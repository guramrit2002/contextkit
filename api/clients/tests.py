import hashlib
import os
import re
from io import StringIO
from unittest import mock

from django.contrib.admin import site
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import SimpleTestCase, TestCase, TransactionTestCase
from django.urls import reverse

from api import settings as project_settings
from clients.models import ApiKey, Client
from clients.services import KEY_PREFIX, create_client, hash_api_key, issue_api_key
from core.auth import authenticate_client
from core.config import REPO_ROOT, resolve_django_db_path


class CreateClientTests(TestCase):
    def test_creates_client_and_returns_plaintext_key(self):
        client, api_key = create_client(user_id="u1", project_id="proj-1", name="builder")

        self.assertEqual(Client.objects.get().project_id, "proj-1")
        self.assertTrue(api_key.startswith(KEY_PREFIX))
        self.assertGreater(len(api_key), 40)

    def test_stores_only_the_sha256_hash(self):
        client, api_key = create_client(user_id="u1", project_id="proj-1", name="builder")

        stored = ApiKey.objects.get(client=client)
        self.assertEqual(stored.key_hash, hashlib.sha256(api_key.encode()).hexdigest())
        self.assertNotIn(api_key, stored.key_hash)

    def test_ids_are_string_uuids(self):
        client, _ = create_client(user_id="u1", project_id="proj-1", name="builder")

        self.assertEqual(len(client.id), 36)
        self.assertEqual(len(client.api_key.id), 36)

    def test_keys_are_unique_per_client(self):
        _, key_a = create_client(user_id="u1", project_id="proj-1", name="a")
        _, key_b = create_client(user_id="u1", project_id="proj-2", name="b")

        self.assertNotEqual(key_a, key_b)

    def test_one_client_per_user_and_project(self):
        create_client(user_id="u1", project_id="proj-1", name="a")

        with self.assertRaises(ValidationError):
            create_client(user_id="u1", project_id="proj-1", name="b")
        self.assertEqual(Client.objects.count(), 1)
        self.assertEqual(ApiKey.objects.count(), 1)

    def test_same_project_allowed_for_different_users(self):
        create_client(user_id="alice", project_id="proj-1", name="a")
        create_client(user_id="bob", project_id="proj-1", name="b")

        self.assertEqual(Client.objects.count(), 2)

    def test_rejects_blank_fields(self):
        for kwargs in (
            {"user_id": " ", "project_id": "p", "name": "n"},
            {"user_id": "u", "project_id": "", "name": "n"},
            {"user_id": "u", "project_id": "p", "name": "  "},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValidationError):
                create_client(**kwargs)
        self.assertEqual(Client.objects.count(), 0)

    def test_strips_whitespace(self):
        client, _ = create_client(user_id=" u1 ", project_id=" proj-1 ", name=" builder ")

        fields = (client.user_id, client.project_id, client.name)
        self.assertEqual(fields, ("u1", "proj-1", "builder"))


class IssueApiKeyTests(TestCase):
    def test_reissue_replaces_previous_key(self):
        client, old_key = create_client(user_id="u1", project_id="proj-1", name="builder")

        new_key = issue_api_key(client)

        self.assertNotEqual(old_key, new_key)
        self.assertEqual(ApiKey.objects.count(), 1)
        self.assertEqual(ApiKey.objects.get().key_hash, hash_api_key(new_key))

    def test_deleting_client_deletes_its_key(self):
        client, _ = create_client(user_id="u1", project_id="proj-1", name="builder")

        client.delete()

        self.assertEqual(ApiKey.objects.count(), 0)


class CreateClientCommandTests(TestCase):
    def test_prints_key_once_and_stores_hash(self):
        out = StringIO()

        call_command(
            "create_client", "--project-id", "proj-1", "--name", "builder", "--user-id", "u1",
            stdout=out,
        )

        output = out.getvalue()
        key_line = next(line for line in output.splitlines() if line.startswith("API key:"))
        api_key = key_line.split(":", 1)[1].strip()
        self.assertEqual(ApiKey.objects.get().key_hash, hash_api_key(api_key))
        self.assertIn("cannot be shown again", output)

    def test_user_id_defaults_to_environment(self):
        with mock.patch.dict("os.environ", {"DEFAULT_USER_ID": "env_user"}):
            call_command(
                "create_client", "--project-id", "proj-1", "--name", "builder", stdout=StringIO()
            )

        self.assertEqual(Client.objects.get().user_id, "env_user")

    def test_duplicate_client_is_a_command_error(self):
        args = ("create_client", "--project-id", "proj-1", "--name", "a", "--user-id", "u1")
        call_command(*args, stdout=StringIO())

        with self.assertRaises(CommandError):
            call_command(*args, stdout=StringIO())


class DatabasePathTests(SimpleTestCase):
    def test_django_uses_the_file_core_reads_clients_from(self):
        # Test runs swap NAME for the test DB, so compare the resolver Django is configured with.
        self.assertIs(project_settings.resolve_django_db_path, resolve_django_db_path)
        self.assertEqual(project_settings.REPO_ROOT, REPO_ROOT)

    def test_database_url_selects_postgres_with_ssl_and_persistent_connections(self):
        db = project_settings.database_settings(
            "postgresql://postgres.ref:pw@aws-0-ap.pooler.supabase.com:5432/postgres"
        )

        self.assertEqual(db["ENGINE"], "django.db.backends.postgresql")
        self.assertEqual((db["HOST"], db["PORT"]), ("aws-0-ap.pooler.supabase.com", 5432))
        self.assertEqual(db["CONN_MAX_AGE"], 60)
        self.assertEqual(db["OPTIONS"]["sslmode"], "require")

    def test_no_database_url_is_refused_outside_tests(self):
        with mock.patch.dict("os.environ", {"CONTEXTKIT_ALLOW_SQLITE": "false"}):
            with self.assertRaisesMessage(ImproperlyConfigured, "DATABASE_URL is not set"):
                project_settings.database_settings("")

    def test_test_runs_opt_in_to_sqlite(self):
        self.assertEqual(os.environ.get("CONTEXTKIT_ALLOW_SQLITE"), "true")

    def test_sqlite_settings_when_allowed(self):
        db = project_settings.database_settings("")

        self.assertEqual(db["ENGINE"], "django.db.backends.sqlite3")
        self.assertEqual(db["NAME"], resolve_django_db_path())

    def test_test_runs_never_use_the_hosted_database(self):
        # settings.py drops DATABASE_URL for `manage.py test`, even when .env sets it.
        self.assertNotIn("DATABASE_URL", os.environ)
        self.assertEqual(
            project_settings.DATABASES["default"]["ENGINE"], "django.db.backends.sqlite3"
        )


class LegacyAgentsMigrationTests(TransactionTestCase):
    """ADR 025: a database migrated by the former `agents` app keeps every client and key."""

    LEGACY_KEY = "ck_legacy_key"

    def migrate(self, target):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(target)

    def build_legacy_database(self):
        self.migrate([("clients", None)])
        # Content types are created after migrations, so a legacy DB has only the agents ones.
        ContentType.objects.filter(app_label="clients").delete()
        agent_ct = ContentType.objects.create(app_label="agents", model="agent")
        ContentType.objects.create(app_label="agents", model="apikey")
        Permission.objects.create(content_type=agent_ct, codename="add_agent", name="Can add agent")
        with connection.cursor() as cursor:
            cursor.execute(
                "CREATE TABLE agents (id varchar(36) PRIMARY KEY, user_id varchar(255) NOT NULL, "
                "project_id varchar(500) NOT NULL, name varchar(255) NOT NULL, "
                "created_at datetime NOT NULL, updated_at datetime NOT NULL, "
                "CONSTRAINT uniq_agent_user_project UNIQUE (user_id, project_id))"
            )
            cursor.execute(
                "CREATE TABLE api_keys (id varchar(36) PRIMARY KEY, "
                "key_hash varchar(64) NOT NULL UNIQUE, created_at datetime NOT NULL, "
                "agent_id varchar(36) NOT NULL UNIQUE REFERENCES agents (id))"
            )
            cursor.execute(
                "INSERT INTO agents VALUES ('legacy-1', 'alice', 'proj-1', 'old-bot', "
                "'2026-09-01 00:00:00', '2026-09-01 00:00:00')"
            )
            cursor.execute(
                "INSERT INTO api_keys VALUES ('key-1', %s, '2026-09-01 00:00:00', 'legacy-1')",
                [hash_api_key(self.LEGACY_KEY)],
            )
        return agent_ct

    def test_existing_clients_and_keys_survive_the_rename(self):
        agent_ct = self.build_legacy_database()

        self.migrate([("clients", "0001_initial")])

        client = Client.objects.get()
        self.assertEqual((client.id, client.user_id, client.name), ("legacy-1", "alice", "old-bot"))
        self.assertEqual(client.api_key.key_hash, hash_api_key(self.LEGACY_KEY))
        tables = set(connection.introspection.table_names())
        self.assertFalse({"agents", "api_keys_legacy"} & tables)

        with mock.patch.dict("os.environ", {"DJANGO_DB_PATH": connection.settings_dict["NAME"]}):
            context = authenticate_client(self.LEGACY_KEY)
        self.assertEqual((context.client_id, context.project_id), ("legacy-1", "proj-1"))

        renamed = ContentType.objects.get(app_label="clients", model="client")
        self.assertEqual(renamed.id, agent_ct.id)
        self.assertFalse(ContentType.objects.filter(app_label="agents").exists())
        self.assertTrue(Permission.objects.filter(content_type=renamed, codename="add_client"))

    def test_uniqueness_still_enforced_after_carry_over(self):
        self.build_legacy_database()
        self.migrate([("clients", "0001_initial")])

        with self.assertRaises(ValidationError):
            create_client(user_id="alice", project_id="proj-1", name="dup")


class ClientAdminTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("admin", "admin@example.com", "pw")
        self.client.force_login(self.admin)

    def issued_keys(self, response):
        return re.findall(r'<code class="issued-api-key">([^<]+)</code>', response.content.decode())

    def test_adding_a_client_issues_a_key_and_shows_it_once(self):
        response = self.client.post(reverse("admin:clients_client_add"), {
            "name": "ci-bot", "user_id": "alice", "project_id": "proj-1",
        })

        self.assertEqual(response.status_code, 200)
        [api_key] = self.issued_keys(response)
        client = Client.objects.get()
        self.assertEqual(client.api_key.key_hash, hash_api_key(api_key))
        self.assertNotIn("messages", response.cookies)
        self.assertNotIn(api_key, str(dict(self.client.session)))

        listing = self.client.get(reverse("admin:clients_client_changelist"))
        self.assertNotIn(api_key, listing.content.decode())

    def test_editing_a_client_keeps_its_key(self):
        client, api_key = create_client(user_id="alice", project_id="proj-1", name="bot")

        response = self.client.post(reverse("admin:clients_client_change", args=[client.id]), {
            "name": "renamed", "user_id": "alice", "project_id": "proj-1",
        })

        self.assertEqual(response.status_code, 302)
        self.assertEqual(ApiKey.objects.get().key_hash, hash_api_key(api_key))

    def test_regenerate_action_replaces_keys_and_shows_them(self):
        client_a, old_a = create_client(user_id="alice", project_id="proj-1", name="a")
        client_b, _ = create_client(user_id="alice", project_id="proj-2", name="b")

        response = self.client.post(reverse("admin:clients_client_changelist"), {
            "action": "regenerate_api_keys", "_selected_action": [client_a.id, client_b.id],
        })

        new_keys = self.issued_keys(response)
        self.assertEqual(len(new_keys), 2)
        self.assertNotIn(old_a, new_keys)
        hashes = set(ApiKey.objects.values_list("key_hash", flat=True))
        self.assertEqual(hashes, {hash_api_key(k) for k in new_keys})

    def test_regenerate_repairs_a_client_with_an_empty_key(self):
        client = Client.objects.create(user_id="alice", project_id="proj-1", name="broken")
        ApiKey.objects.create(client=client, key_hash="")

        response = self.client.post(reverse("admin:clients_client_changelist"), {
            "action": "regenerate_api_keys", "_selected_action": [client.id],
        })

        [api_key] = self.issued_keys(response)
        self.assertEqual(ApiKey.objects.get().key_hash, hash_api_key(api_key))

    def test_changelist_shows_whether_a_client_has_a_key(self):
        client = Client.objects.create(user_id="alice", project_id="proj-1", name="no-key")
        admin_obj = site._registry[Client]

        self.assertFalse(admin_obj.has_key(client))
        issue_api_key(client)
        client.refresh_from_db()
        self.assertTrue(admin_obj.has_key(client))

    def test_api_keys_cannot_be_added_or_edited_in_admin(self):
        client, _ = create_client(user_id="alice", project_id="proj-1", name="bot")
        key = ApiKey.objects.get()

        self.assertEqual(self.client.get(reverse("admin:clients_apikey_add")).status_code, 403)
        change_url = reverse("admin:clients_apikey_change", args=[key.id])
        self.assertEqual(self.client.get(change_url).status_code, 200)
        response = self.client.post(change_url, {"key_hash": "tampered"})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(ApiKey.objects.get().key_hash, key.key_hash)
