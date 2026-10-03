import os
import sqlite3
import tempfile
from pathlib import Path
from unittest import mock

from django.core import checks
from django.db import connection
from django.test import SimpleTestCase, TransactionTestCase
from rest_framework.test import APIClient

from clients.services import create_client
from context.checks import core_database_schema
from core.db_init import SchemaStatus, initialize_database

BASE = "/api/agent/v1/context"
CORE_TABLES = {"projects", "decisions", "state", "sessions", "audit_log", "alembic_version"}


class ContextApiTestCase(TransactionTestCase):
    """
    Core gets its own fresh database per test; Django's test database holds the clients.
    TransactionTestCase so the client rows are committed: core reads them through its own
    read-only connection to Django's file.
    """

    def setUp(self):
        core_dir = tempfile.TemporaryDirectory()
        self.addCleanup(core_dir.cleanup)
        self.db_path = str(Path(core_dir.name) / "core.sqlite3")
        self.django_db_path = connection.settings_dict["NAME"]
        env = mock.patch.dict(os.environ, {
            "CONTEXTKIT_DB_PATH": self.db_path,
            "DJANGO_DB_PATH": self.django_db_path,
        })
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("REQUIRE_AUTH", None)
        initialize_database()

        self.client_record, self.key = create_client(
            user_id="alice", project_id="proj-1", name="ci-bot"
        )
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.key}")

    def query(self, sql):
        with sqlite3.connect(self.db_path) as conn:
            return conn.execute(sql).fetchall()

    def audit(self):
        return self.query(
            "SELECT tool_name, status, client_id, project_id FROM audit_log ORDER BY timestamp"
        )


class EndpointTests(ContextApiTestCase):
    def test_briefing_returns_assigned_project(self):
        response = self.client.get(f"{BASE}/briefing/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["project"]["id"], "proj-1")
        expected = [("get_context", "success", self.client_record.id, "proj-1")]
        self.assertEqual(self.audit(), expected)

    def test_log_decision(self):
        response = self.client.post(
            f"{BASE}/decisions/",
            {
                "decision": "Use DRF",
                "reasoning": "Agents without MCP",
                "alternatives_considered": "Flask",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertTrue(body["success"])
        self.assertTrue(body["decision_id"])
        self.assertTrue(body["created_at"])
        rows = self.query(
            "SELECT project_id, client_id, user_id, alternatives_considered FROM decisions"
        )
        self.assertEqual(rows, [("proj-1", self.client_record.id, "alice", "Flask")])
        expected = [("log_decision", "success", self.client_record.id, "proj-1")]
        self.assertEqual(self.audit(), expected)

    def test_update_state(self):
        response = self.client.post(
            f"{BASE}/state/", {"progress": "REST done", "next_steps": "Docs"}, format="json"
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["updated_at"])
        self.assertEqual(
            self.query("SELECT project_id, user_id, progress, blockers FROM state"),
            [("proj-1", "alice", "REST done", None)],
        )

    def test_log_session(self):
        body = {"summary": "Built REST API", "decisions_made": "DRF"}

        response = self.client.post(f"{BASE}/sessions/", body, format="json")

        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.json()["session_id"])
        self.assertEqual(
            self.query("SELECT project_id, client_id, summary FROM sessions"),
            [("proj-1", self.client_record.id, "Built REST API")],
        )

    def test_export_markdown(self):
        self.client.post(f"{BASE}/decisions/", {"decision": "D", "reasoning": "R"}, format="json")

        response = self.client.post(f"{BASE}/export/", {}, format="json")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["format"], "markdown")
        self.assertIn("`proj-1`", body["content"])
        self.assertEqual(body["size_bytes"], len(body["content"].encode("utf-8")))

    def test_explicit_matching_project_is_allowed(self):
        response = self.client.get(f"{BASE}/briefing/", {"project_id": "proj-1"})

        self.assertEqual(response.status_code, 200)

    def test_null_project_means_assigned_project(self):
        response = self.client.post(
            f"{BASE}/sessions/", {"summary": "s", "project_id": None}, format="json"
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(self.query("SELECT project_id FROM sessions"), [("proj-1",)])

    def test_secrets_are_redacted_before_storage(self):
        self.client.post(
            f"{BASE}/decisions/",
            {"decision": "Rotate creds", "reasoning": "old one was password=hunter2"},
            format="json",
        )

        [(reasoning,)] = self.query("SELECT reasoning FROM decisions")
        self.assertNotIn("hunter2", reasoning)


class AuthenticationTests(ContextApiTestCase):
    def assert_denied_401(self, response):
        self.assertEqual(response.status_code, 401)
        self.assertTrue(response["WWW-Authenticate"].startswith("Bearer"))

    def test_missing_key_is_401_and_audited(self):
        self.client.credentials()

        response = self.client.post(
            f"{BASE}/decisions/", {"decision": "d", "reasoning": "r"}, format="json"
        )

        self.assert_denied_401(response)
        self.assertEqual(self.audit(), [("log_decision", "denied", None, None)])
        self.assertEqual(self.query("SELECT COUNT(*) FROM decisions"), [(0,)])

    def test_missing_key_is_401_even_when_auth_not_required(self):
        self.client.credentials()

        with mock.patch.dict(os.environ, {"REQUIRE_AUTH": "false"}):
            response = self.client.get(f"{BASE}/briefing/")

        self.assert_denied_401(response)

    def test_invalid_key_is_401_and_audited(self):
        self.client.credentials(HTTP_AUTHORIZATION="Bearer ck_not_a_real_key")

        response = self.client.get(f"{BASE}/briefing/", {"project_id": "proj-1"})

        self.assert_denied_401(response)
        self.assertEqual(response.json()["detail"], "Invalid API key")
        self.assertEqual(self.audit(), [("get_context", "denied", None, "proj-1")])

    def test_non_bearer_header_is_401(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Basic {self.key}")

        self.assert_denied_401(self.client.get(f"{BASE}/briefing/"))

    def test_revoked_key_stops_working(self):
        self.client_record.delete()

        self.assert_denied_401(self.client.get(f"{BASE}/briefing/"))


class ProjectAccessTests(ContextApiTestCase):
    def test_other_project_is_403_on_every_endpoint(self):
        other = {"project_id": "proj-2"}
        calls = [
            ("get_context", lambda: self.client.get(f"{BASE}/briefing/", other)),
            ("log_decision", lambda: self.client.post(
                f"{BASE}/decisions/", {**other, "decision": "d", "reasoning": "r"}, format="json")),
            ("update_state", lambda: self.client.post(
                f"{BASE}/state/", {**other, "progress": "p", "next_steps": "n"}, format="json")),
            ("log_session", lambda: self.client.post(
                f"{BASE}/sessions/", {**other, "summary": "s"}, format="json")),
            ("export_markdown", lambda: self.client.post(f"{BASE}/export/", other, format="json")),
        ]

        for tool_name, call in calls:
            with self.subTest(tool=tool_name):
                response = call()
                self.assertEqual(response.status_code, 403)
                self.assertIn("proj-2", response.json()["detail"])

        self.assertEqual(
            self.audit(), [(tool, "denied", self.client_record.id, "proj-2") for tool, _ in calls]
        )
        self.assertEqual(self.query("SELECT COUNT(*) FROM decisions"), [(0,)])

    def test_clients_are_isolated_from_each_other(self):
        _, bob_key = create_client(user_id="bob", project_id="proj-bob", name="bob-bot")
        self.client.post(
            f"{BASE}/decisions/", {"decision": "alice", "reasoning": "r"}, format="json"
        )

        bob = APIClient()
        bob.credentials(HTTP_AUTHORIZATION=f"Bearer {bob_key}")
        briefing = bob.get(f"{BASE}/briefing/").json()

        self.assertEqual(briefing["project"]["id"], "proj-bob")
        self.assertEqual(briefing["decisions"], [])


class DatabaseSeparationTests(ContextApiTestCase):
    def tables(self, path):
        with sqlite3.connect(path) as conn:
            return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}

    def test_core_and_django_tables_live_in_separate_files(self):
        self.client.post(f"{BASE}/decisions/", {"decision": "d", "reasoning": "r"}, format="json")

        core_tables = self.tables(self.db_path)
        django_tables = self.tables(self.django_db_path)
        self.assertEqual(core_tables, CORE_TABLES)
        self.assertIn("clients", django_tables)
        self.assertIn("api_keys", django_tables)
        self.assertFalse(core_tables & django_tables)


class ErrorHandlingTests(ContextApiTestCase):
    def test_missing_required_field_is_400(self):
        response = self.client.post(f"{BASE}/decisions/", {"decision": "d"}, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertIn("reasoning", response.json())

    def test_unsupported_export_format_is_400(self):
        response = self.client.post(f"{BASE}/export/", {"format": "pdf"}, format="json")

        self.assertEqual(response.status_code, 400)

    def test_core_validation_error_is_400_and_audited(self):
        response = self.client.post(
            f"{BASE}/decisions/", {"decision": "x" * 5001, "reasoning": "r"}, format="json"
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("maximum length", response.json()["detail"])
        self.assertEqual(self.audit(), [("log_decision", "error", self.client_record.id, "proj-1")])

    def test_unexpected_failure_is_500_without_leaking_details(self):
        with mock.patch(
            "core.services.log_session", side_effect=RuntimeError("db at /secret/path")
        ):
            response = self.client.post(f"{BASE}/sessions/", {"summary": "s"}, format="json")

        self.assertEqual(response.status_code, 500)
        self.assertNotIn("/secret/path", response.content.decode())
        self.assertEqual(self.audit(), [("log_session", "error", self.client_record.id, "proj-1")])

    def test_wrong_method_is_405(self):
        self.assertEqual(self.client.get(f"{BASE}/decisions/").status_code, 405)


class CoreSchemaCheckTests(SimpleTestCase):
    def run_check(self, current, has_tables=True):
        status = SchemaStatus(current, "0003", has_tables)
        with mock.patch("context.checks.core_schema_status", return_value=status):
            return core_database_schema(None)

    def test_up_to_date_database_passes(self):
        self.assertEqual(self.run_check("0003"), [])

    def test_database_behind_is_an_error_with_the_upgrade_command(self):
        [issue] = self.run_check("0002")

        self.assertEqual((issue.level, issue.id), (checks.ERROR, "context.E001"))
        self.assertIn("0002", issue.msg)
        self.assertIn("alembic upgrade head", issue.hint)

    def test_pre_alembic_database_is_an_error(self):
        [issue] = self.run_check(None, has_tables=True)

        self.assertEqual(issue.id, "context.E001")
        self.assertIn("pre-Alembic", issue.msg)

    def test_missing_database_is_only_a_warning(self):
        [issue] = self.run_check(None, has_tables=False)

        self.assertEqual((issue.level, issue.id), (checks.WARNING, "context.W001"))

    def test_check_is_registered(self):
        self.assertIn(core_database_schema, checks.registry.registry.get_checks())

    def test_postgres_is_named_without_the_url_or_a_sqlite_path(self):
        # The error used to name core.sqlite3 even when the database was Supabase.
        url = "postgresql+psycopg://user:secret-pw@pooler.example.com:5432/postgres"
        with mock.patch("core.config.resolve_database_url", return_value=url):
            [issue] = self.run_check("0002")

        self.assertIn("Core database (Postgres database from DATABASE_URL)", issue.msg)
        self.assertNotIn("sqlite", issue.msg)
        self.assertNotIn("secret-pw", issue.msg)
        self.assertNotIn("pooler.example.com", issue.msg)

    def test_sqlite_is_named_by_its_file(self):
        with mock.patch("core.config.resolve_database_url", return_value="sqlite:////tmp/core.sqlite3"):
            [issue] = self.run_check("0002")

        self.assertIn("Core database (SQLite file /tmp/core.sqlite3)", issue.msg)


class CoreDatabaseUnreachableTests(SimpleTestCase):
    def test_unreachable_database_is_one_clean_error_without_the_url(self):
        from sqlalchemy.exc import OperationalError

        failure = OperationalError(
            "SELECT 1", {}, Exception("connection to postgres://u:secret@db.invalid failed")
        )
        with mock.patch("context.checks.core_schema_status", side_effect=failure):
            [issue] = core_database_schema(None)

        self.assertEqual((issue.level, issue.id), (checks.ERROR, "context.E002"))
        self.assertNotIn("secret", issue.msg + issue.hint)
        self.assertNotIn("db.invalid", issue.msg + issue.hint)
