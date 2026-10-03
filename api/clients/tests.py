import hashlib
import os
import re
from io import StringIO
from unittest import mock

from django.contrib.admin import site
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.core import checks
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import SimpleTestCase, TestCase, TransactionTestCase
from django.urls import reverse

from accounts import github
from api import settings as project_settings
from clients.checks import shared_projects
from clients.models import ApiKey, Client
from clients.services import (
    KEY_PREFIX,
    OTHER_OWNER_MESSAGE,
    create_client,
    hash_api_key,
    issue_api_key,
)
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

    def test_the_same_name_twice_in_a_project_is_refused(self):
        create_client(user_id="u1", project_id="proj-1", name="a")

        with self.assertRaises(ValidationError):
            create_client(user_id="u1", project_id="proj-1", name="a")
        self.assertEqual(Client.objects.count(), 1)
        self.assertEqual(ApiKey.objects.count(), 1)

    def test_a_project_belongs_to_one_user_even_for_operators(self):
        create_client(user_id="alice", project_id="proj-1", name="a")

        with self.assertRaisesMessage(ValidationError, OTHER_OWNER_MESSAGE):
            create_client(user_id="bob", project_id="proj-1", name="b")
        self.assertEqual(Client.objects.count(), 1)

    def test_operator_path_skips_the_github_check(self):
        with mock.patch.object(github, "fetch_public_repo") as lookup:
            create_client(user_id="u1", project_id="https://github.com/someone/else", name="a")

        lookup.assert_not_called()

    def test_rejects_blank_fields(self):
        for kwargs in (
            {"user_id": " ", "project_id": "p", "name": "n"},
            {"user_id": "u", "project_id": "", "name": "n"},
            {"user_id": "u", "project_id": "p", "name": "  "},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValidationError):
                create_client(**kwargs)
        self.assertEqual(Client.objects.count(), 0)

    def test_stores_the_canonical_project_id(self):
        client, _ = create_client(user_id="u1", project_id="git@github.com:Acme/App.git", name="a")

        self.assertEqual(client.project_id, "https://github.com/acme/app")
        self.assertEqual(Client.objects.get().project_id, "https://github.com/acme/app")

    def test_a_name_is_unique_per_project_in_any_url_form_or_case(self):
        create_client(user_id="u1", project_id="https://github.com/acme/app", name="Codex")

        with self.assertRaisesMessage(ValidationError, "already has a key named CODEX"):
            create_client(user_id="u1", project_id="git@github.com:acme/app.git", name="CODEX")
        create_client(user_id="u1", project_id="https://github.com/acme/app", name="Cursor")
        self.assertEqual(Client.objects.count(), 2)

    def test_the_database_enforces_unique_names_ignoring_case(self):
        from django.db import IntegrityError, transaction

        Client.objects.create(user_id="u1", project_id="p", name="Codex")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Client.objects.create(user_id="u1", project_id="p", name="codex")

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


def migrate_to_latest():
    executor = MigrationExecutor(connection)
    executor.migrate(executor.loader.graph.leaf_nodes())


class LegacyAgentsMigrationTests(TransactionTestCase):
    """ADR 025: a database migrated by the former `agents` app keeps every client and key."""

    LEGACY_KEY = "ck_legacy_key"

    def migrate(self, target):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(target)

    def tearDown(self):
        migrate_to_latest()

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
            create_client(user_id="alice", project_id="proj-1", name="old-bot")


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

    def test_adding_a_client_stores_the_canonical_project_id(self):
        self.client.post(reverse("admin:clients_client_add"), {
            "name": "ci-bot", "user_id": "alice", "project_id": "git@github.com:Acme/App.git",
        })

        self.assertEqual(Client.objects.get().project_id, "https://github.com/acme/app")

    def test_admin_refuses_a_duplicate_name_in_any_url_form_or_case(self):
        create_client(user_id="alice", project_id="https://github.com/acme/app", name="bot")

        response = self.client.post(reverse("admin:clients_client_add"), {
            "name": "BOT", "user_id": "alice", "project_id": "github.com/acme/app",
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Client.objects.count(), 1)
        self.assertTrue(response.context["adminform"].form.errors)

    def test_admin_shows_the_one_owner_error(self):
        create_client(user_id="alice", project_id="https://github.com/acme/app", name="bot")

        response = self.client.post(reverse("admin:clients_client_add"), {
            "name": "other", "user_id": "bob", "project_id": "git@github.com:acme/app.git",
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, OTHER_OWNER_MESSAGE)
        self.assertEqual(Client.objects.count(), 1)

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


class NormalizeProjectIdsMigrationTests(TransactionTestCase):
    """ADR 030: clients are moved to canonical project IDs; collisions stop the migration."""

    def migrate(self, target):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(target)

    def tearDown(self):
        migrate_to_latest()

    def add(self, client_id, user_id, project_id):
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO clients (id, user_id, project_id, name, created_at, updated_at) "
                "VALUES (%s, %s, %s, %s, '2026-09-01 00:00:00', '2026-09-01 00:00:00')",
                [client_id, user_id, project_id, f"name-{client_id}"],
            )

    def test_project_ids_are_normalized(self):
        self.migrate([("clients", "0001_initial")])
        self.add("c1", "alice", "https://github.com/Acme/App.git")
        self.add("c2", "alice", "local-proj")
        self.add("c3", "bob", "git@github.com:acme/app.git")

        self.migrate([("clients", "0002_normalize_project_ids")])

        self.assertEqual(
            dict(Client.objects.values_list("id", "project_id")),
            {
                "c1": "https://github.com/acme/app",
                "c2": "local-proj",
                "c3": "https://github.com/acme/app",
            },
        )

    def test_same_user_collision_raises_and_deletes_nothing(self):
        self.migrate([("clients", "0001_initial")])
        self.add("c1", "alice", "https://github.com/acme/app")
        self.add("c2", "alice", "git@github.com:acme/app.git")

        with self.assertRaises(RuntimeError) as caught:
            self.migrate([("clients", "0002_normalize_project_ids")])

        message = str(caught.exception)
        self.assertIn("c1 ('name-c1'", message)
        self.assertIn("c2 ('name-c2'", message)

        self.assertEqual(Client.objects.count(), 2)
        Client.objects.filter(id="c2").delete()  # the operator revokes one, then reruns


class SharedProjectsCheckTests(TestCase):
    """clients.W002 reports projects held by more than one user and changes nothing."""

    def test_lists_a_shared_project_and_changes_nothing(self):
        # Created directly: the services no longer allow this, but old data may contain it.
        Client.objects.create(user_id="1", project_id="https://github.com/acme/app", name="a")
        Client.objects.create(user_id="2", project_id="https://github.com/acme/app", name="b")
        Client.objects.create(user_id="1", project_id="https://github.com/acme/solo", name="c")

        [warning] = shared_projects(None, databases=["default"])

        self.assertEqual(warning.id, "clients.W002")
        self.assertIn("https://github.com/acme/app", warning.msg)
        self.assertNotIn("acme/solo", warning.msg)
        self.assertIn("revoke the clients that don't belong", warning.hint)
        self.assertEqual(Client.objects.count(), 3)

    def test_silent_without_shared_projects_or_outside_database_checks(self):
        Client.objects.create(user_id="1", project_id="https://github.com/acme/app", name="a")

        self.assertEqual(shared_projects(None, databases=["default"]), [])
        self.assertEqual(shared_projects(None, databases=None), [])

    def test_registered_for_database_checks(self):
        Client.objects.create(user_id="1", project_id="p", name="a")
        Client.objects.create(user_id="2", project_id="p", name="b")

        ids = [m.id for m in checks.run_checks(tags=[checks.Tags.database], databases=["default"])]
        self.assertIn("clients.W002", ids)


class ClientsPerProjectMigrationTests(TransactionTestCase):
    """clients 0003 (ADR 031): existing clients survive; many per project afterwards."""

    def migrate(self, target):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(target)

    def tearDown(self):
        Client.objects.all().delete()
        migrate_to_latest()

    def add(self, client_id, user_id, project_id, name):
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO clients (id, user_id, project_id, name, created_at, updated_at) "
                "VALUES (%s, %s, %s, %s, '2026-09-01 00:00:00', '2026-09-01 00:00:00')",
                [client_id, user_id, project_id, name],
            )

    def test_applies_with_existing_clients_and_then_allows_several_per_project(self):
        self.migrate([("clients", "0002_normalize_project_ids")])
        self.add("c1", "alice", "https://github.com/acme/app", "laptop")
        self.add("c2", "bob", "https://github.com/bob/app", "laptop")

        self.migrate([("clients", "0003_clients_per_project")])

        self.assertEqual(Client.objects.count(), 2)
        self.add("c3", "alice", "https://github.com/acme/app", "Codex")
        self.assertEqual(Client.objects.filter(project_id="https://github.com/acme/app").count(), 2)

    def test_reverse_refuses_clearly_while_a_project_has_several_clients(self):
        self.migrate([("clients", "0003_clients_per_project")])
        self.add("c1", "alice", "p", "Claude Code")
        self.add("c2", "alice", "p", "Codex")

        with self.assertRaisesMessage(RuntimeError, "Revoke the extra clients first"):
            self.migrate([("clients", "0002_normalize_project_ids")])
        self.assertEqual(Client.objects.count(), 2)

    def test_reverse_works_with_one_client_per_project(self):
        self.migrate([("clients", "0003_clients_per_project")])
        self.add("c1", "alice", "p", "Claude Code")

        self.migrate([("clients", "0002_normalize_project_ids")])

        self.assertEqual(Client.objects.count(), 1)


class KeyNameTests(TestCase):
    """`<project>-<client>-<key-id>` (user API and website)."""

    def test_builds_from_repository_client_and_id(self):
        from clients.services import key_name

        client_id = "3f9a1c2b-0000-4000-8000-000000000000"
        cases = [
            ("https://github.com/acme/contextkit", "Claude Code", "contextkit-claude-code"),
            ("https://github.com/acme/my.app", "VS Code (Copilot)", "my-app-vs-code-copilot"),
            ("/Users/me/Side Project/", "ci bot", "side-project-ci-bot"),
            ("https://github.com/acme/app", "***", "app-client"),
        ]
        for project_id, client, expected in cases:
            with self.subTest(client=client):
                self.assertEqual(key_name(project_id, client, client_id), f"{expected}-3f9a1c2b")

    def test_operator_paths_keep_the_name_they_are_given(self):
        client, _ = create_client(
            user_id="u1", project_id="https://github.com/acme/app", name="ci-bot"
        )

        self.assertEqual(client.name, "ci-bot")
