import hashlib
from io import StringIO
from pathlib import Path
from unittest import mock

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase

from agents.models import Agent, ApiKey
from agents.services import KEY_PREFIX, create_agent, hash_api_key, issue_api_key
from api import settings as project_settings


class CreateAgentTests(TestCase):
    def test_creates_agent_and_returns_plaintext_key(self):
        agent, api_key = create_agent(user_id="u1", project_id="proj-1", name="builder")

        self.assertEqual(Agent.objects.get().project_id, "proj-1")
        self.assertTrue(api_key.startswith(KEY_PREFIX))
        self.assertGreater(len(api_key), 40)

    def test_stores_only_the_sha256_hash(self):
        agent, api_key = create_agent(user_id="u1", project_id="proj-1", name="builder")

        stored = ApiKey.objects.get(agent=agent)
        self.assertEqual(stored.key_hash, hashlib.sha256(api_key.encode()).hexdigest())
        self.assertNotIn(api_key, stored.key_hash)

    def test_ids_are_string_uuids(self):
        agent, _ = create_agent(user_id="u1", project_id="proj-1", name="builder")

        self.assertEqual(len(agent.id), 36)
        self.assertEqual(len(agent.api_key.id), 36)

    def test_keys_are_unique_per_agent(self):
        _, key_a = create_agent(user_id="u1", project_id="proj-1", name="a")
        _, key_b = create_agent(user_id="u1", project_id="proj-2", name="b")

        self.assertNotEqual(key_a, key_b)

    def test_one_agent_per_user_and_project(self):
        create_agent(user_id="u1", project_id="proj-1", name="a")

        with self.assertRaises(ValidationError):
            create_agent(user_id="u1", project_id="proj-1", name="b")
        self.assertEqual(Agent.objects.count(), 1)
        self.assertEqual(ApiKey.objects.count(), 1)

    def test_same_project_allowed_for_different_users(self):
        create_agent(user_id="alice", project_id="proj-1", name="a")
        create_agent(user_id="bob", project_id="proj-1", name="b")

        self.assertEqual(Agent.objects.count(), 2)

    def test_rejects_blank_fields(self):
        for kwargs in (
            {"user_id": " ", "project_id": "p", "name": "n"},
            {"user_id": "u", "project_id": "", "name": "n"},
            {"user_id": "u", "project_id": "p", "name": "  "},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValidationError):
                create_agent(**kwargs)
        self.assertEqual(Agent.objects.count(), 0)

    def test_strips_whitespace(self):
        agent, _ = create_agent(user_id=" u1 ", project_id=" proj-1 ", name=" builder ")

        self.assertEqual((agent.user_id, agent.project_id, agent.name), ("u1", "proj-1", "builder"))


class IssueApiKeyTests(TestCase):
    def test_reissue_replaces_previous_key(self):
        agent, old_key = create_agent(user_id="u1", project_id="proj-1", name="builder")

        new_key = issue_api_key(agent)

        self.assertNotEqual(old_key, new_key)
        self.assertEqual(ApiKey.objects.count(), 1)
        self.assertEqual(ApiKey.objects.get().key_hash, hash_api_key(new_key))

    def test_deleting_agent_deletes_its_key(self):
        agent, _ = create_agent(user_id="u1", project_id="proj-1", name="builder")

        agent.delete()

        self.assertEqual(ApiKey.objects.count(), 0)


class CreateAgentCommandTests(TestCase):
    def test_prints_key_once_and_stores_hash(self):
        out = StringIO()

        call_command(
            "create_agent", "--project-id", "proj-1", "--name", "builder", "--user-id", "u1",
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
                "create_agent", "--project-id", "proj-1", "--name", "builder", stdout=StringIO()
            )

        self.assertEqual(Agent.objects.get().user_id, "env_user")

    def test_duplicate_agent_is_a_command_error(self):
        args = ("create_agent", "--project-id", "proj-1", "--name", "a", "--user-id", "u1")
        call_command(*args, stdout=StringIO())

        with self.assertRaises(CommandError):
            call_command(*args, stdout=StringIO())


class DatabasePathTests(SimpleTestCase):
    def test_defaults_to_repo_root_database(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            self.assertEqual(
                project_settings._contextkit_db_path(), project_settings.REPO_ROOT / "db.sqlite3"
            )

    def test_relative_path_resolves_from_repo_root(self):
        with mock.patch.dict("os.environ", {"CONTEXTKIT_DB_PATH": "./data/ck.db"}):
            self.assertEqual(
                project_settings._contextkit_db_path(),
                (project_settings.REPO_ROOT / "data" / "ck.db").resolve(),
            )

    def test_absolute_path_is_used_as_is(self):
        with mock.patch.dict("os.environ", {"CONTEXTKIT_DB_PATH": "/var/lib/ck.db"}):
            self.assertEqual(project_settings._contextkit_db_path(), Path("/var/lib/ck.db"))
