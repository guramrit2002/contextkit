import os
import sqlite3
from unittest import mock

from django.db import connection
from django.test import TransactionTestCase
from rest_framework.test import APIClient

from agents.services import create_agent
from core.db_init import initialize_database

BASE = "/api/agent/v1/context"
CORE_TABLES = ("audit_log", "decisions", "sessions", "state", "projects")


class ContextApiTestCase(TransactionTestCase):
    """
    TransactionTestCase so Django commits the agent rows: core reads them through its own
    connection to the same SQLite file.
    """

    def setUp(self):
        self.db_path = connection.settings_dict["NAME"]
        env = mock.patch.dict(os.environ, {"CONTEXTKIT_DB_PATH": self.db_path})
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("REQUIRE_AUTH", None)

        initialize_database()
        with sqlite3.connect(self.db_path) as conn:
            for table in CORE_TABLES:
                conn.execute(f"DELETE FROM {table}")

        self.agent, self.key = create_agent(user_id="alice", project_id="proj-1", name="ci-bot")
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.key}")

    def query(self, sql):
        with sqlite3.connect(self.db_path) as conn:
            return conn.execute(sql).fetchall()

    def audit(self):
        return self.query(
            "SELECT tool_name, status, agent_id, project_id FROM audit_log ORDER BY timestamp"
        )


class EndpointTests(ContextApiTestCase):
    def test_briefing_returns_assigned_project(self):
        response = self.client.get(f"{BASE}/briefing/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["project"]["id"], "proj-1")
        self.assertEqual(self.audit(), [("get_context", "success", self.agent.id, "proj-1")])

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
            "SELECT project_id, agent_id, user_id, alternatives_considered FROM decisions"
        )
        self.assertEqual(rows, [("proj-1", self.agent.id, "alice", "Flask")])
        self.assertEqual(self.audit(), [("log_decision", "success", self.agent.id, "proj-1")])

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
            self.query("SELECT project_id, agent_id, summary FROM sessions"),
            [("proj-1", self.agent.id, "Built REST API")],
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
        self.agent.delete()

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
            self.audit(), [(tool, "denied", self.agent.id, "proj-2") for tool, _ in calls]
        )
        self.assertEqual(self.query("SELECT COUNT(*) FROM decisions"), [(0,)])

    def test_agents_are_isolated_from_each_other(self):
        _, bob_key = create_agent(user_id="bob", project_id="proj-bob", name="bob-bot")
        self.client.post(
            f"{BASE}/decisions/", {"decision": "alice", "reasoning": "r"}, format="json"
        )

        bob = APIClient()
        bob.credentials(HTTP_AUTHORIZATION=f"Bearer {bob_key}")
        briefing = bob.get(f"{BASE}/briefing/").json()

        self.assertEqual(briefing["project"]["id"], "proj-bob")
        self.assertEqual(briefing["decisions"], [])


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
        self.assertEqual(self.audit(), [("log_decision", "error", self.agent.id, "proj-1")])

    def test_unexpected_failure_is_500_without_leaking_details(self):
        with mock.patch(
            "core.services.log_session", side_effect=RuntimeError("db at /secret/path")
        ):
            response = self.client.post(f"{BASE}/sessions/", {"summary": "s"}, format="json")

        self.assertEqual(response.status_code, 500)
        self.assertNotIn("/secret/path", response.content.decode())
        self.assertEqual(self.audit(), [("log_session", "error", self.agent.id, "proj-1")])

    def test_wrong_method_is_405(self):
        self.assertEqual(self.client.get(f"{BASE}/decisions/").status_code, 405)
