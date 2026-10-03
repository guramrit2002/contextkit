"""User API (ADR 028): JWT login and API-key management."""
from unittest import mock

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase, TransactionTestCase, override_settings
from rest_framework.test import APIClient as HttpClient

from accounts import github
from clients.models import ApiKey, Client
from clients.services import (
    GITHUB_UNAVAILABLE_MESSAGE,
    KEY_PREFIX,
    NOT_YOUR_REPO_MESSAGE,
    OTHER_OWNER_MESSAGE,
    create_client,
    hash_api_key,
)
from clients.testing import link_github, stub_github

TOKEN = "/api/v1/auth/token/"
REFRESH = "/api/v1/auth/token/refresh/"
CLIENTS = "/api/v1/clients/"


def detail(client_id):
    return f"{CLIENTS}{client_id}/"


class UserApiMixin:
    def setUp(self):
        cache.clear()  # throttle counters live in the cache
        self.alice = User.objects.create_user("alice", password="alice-pass-123")
        self.bob = User.objects.create_user("bob", password="bob-pass-123")
        self.http = HttpClient()
        # Alice owns github.com/acme/*, Bob owns github.com/bob/* (see clients.testing).
        link_github(self.alice, "acme", 1)
        link_github(self.bob, "bob", 2)
        self.github = stub_github(self)

    def login(self, username="alice", password="alice-pass-123"):
        credentials = {"username": username, "password": password}
        response = self.http.post(TOKEN, credentials, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.http.credentials(HTTP_AUTHORIZATION=f"Bearer {response.json()['access']}")
        return response.json()

    def create(self, project_id="https://github.com/acme/app", name="laptop"):
        return self.http.post(CLIENTS, {"project_id": project_id, "name": name}, format="json")


class UserApiTestCase(UserApiMixin, TestCase):
    pass


class TokenTests(UserApiTestCase):
    def test_login_returns_access_and_refresh_tokens(self):
        tokens = self.login()

        self.assertEqual(set(tokens), {"access", "refresh"})

    def test_wrong_password_is_401(self):
        response = self.http.post(TOKEN, {"username": "alice", "password": "nope"}, format="json")

        self.assertEqual(response.status_code, 401)

    def test_refresh_issues_a_new_access_token(self):
        tokens = self.login()

        response = self.http.post(REFRESH, {"refresh": tokens["refresh"]}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.json())

    def test_login_attempts_are_throttled_at_the_configured_rate(self):
        # settings.py allows 10 login attempts per minute per client IP.
        codes = [
            self.http.post(TOKEN, {"username": "alice", "password": "nope"}, format="json")
            .status_code
            for _ in range(11)
        ]

        self.assertEqual(codes, [401] * 10 + [429])

    def test_throttling_also_blocks_the_right_password(self):
        for _ in range(10):
            self.http.post(TOKEN, {"username": "alice", "password": "nope"}, format="json")

        response = self.http.post(
            TOKEN, {"username": "alice", "password": "alice-pass-123"}, format="json"
        )

        self.assertEqual(response.status_code, 429)


class AuthenticationRequiredTests(UserApiTestCase):
    def test_every_client_endpoint_needs_a_jwt(self):
        client, _ = create_client(user_id=str(self.alice.pk), project_id="p", name="n")
        calls = [
            self.http.get(CLIENTS),
            self.http.post(CLIENTS, {"project_id": "p2", "name": "n"}, format="json"),
            self.http.get(detail(client.id)),
            self.http.delete(detail(client.id)),
            self.http.post(f"{detail(client.id)}rotate/"),
        ]

        self.assertEqual([r.status_code for r in calls], [401] * 5)
        self.assertEqual(Client.objects.count(), 1)

    def test_an_api_key_is_not_a_login(self):
        _, api_key = create_client(user_id=str(self.alice.pk), project_id="p", name="n")
        self.http.credentials(HTTP_AUTHORIZATION=f"Bearer {api_key}")

        self.assertEqual(self.http.get(CLIENTS).status_code, 401)

    def test_session_login_is_not_accepted(self):
        self.http.force_login(self.alice)

        self.assertEqual(self.http.get(CLIENTS).status_code, 401)


class CreateTests(UserApiTestCase):
    def test_create_returns_the_key_once_and_stores_only_its_hash(self):
        self.login()

        response = self.create()

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response["Cache-Control"], "no-store")
        body = response.json()
        self.assertTrue(body["api_key"].startswith(KEY_PREFIX))
        self.assertTrue(body["has_key"])
        client = Client.objects.get(id=body["id"])
        self.assertEqual(client.user_id, str(self.alice.pk))
        self.assertEqual(client.api_key.key_hash, hash_api_key(body["api_key"]))
        self.assertNotIn("key_hash", body)

    def test_the_key_is_never_shown_again(self):
        self.login()
        created = self.create().json()

        listing = self.http.get(CLIENTS).content.decode()
        single = self.http.get(detail(created["id"])).content.decode()

        for body in (listing, single):
            self.assertNotIn(created["api_key"], body)
            self.assertNotIn("api_key", body)
            self.assertNotIn("key_hash", body)

    def test_a_project_can_have_a_key_per_agent(self):
        self.login()
        self.create(name="Claude Code")

        response = self.create(name="Codex")

        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            sorted(Client.objects.values_list("name", flat=True)), ["Claude Code", "Codex"]
        )

    def test_create_stores_and_returns_the_canonical_project_id(self):
        self.login()

        response = self.create(project_id="git@github.com:Acme/App.git")

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["project_id"], "https://github.com/acme/app")
        self.assertEqual(Client.objects.get().project_id, "https://github.com/acme/app")

    def test_same_name_in_any_case_or_url_form_is_refused_under_name(self):
        self.login()
        self.create(project_id="https://github.com/acme/app", name="Claude Code")

        response = self.create(project_id="git@github.com:acme/app.git", name="  claude code ")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"name": [
            "This project already has a key named claude code. Rotate it, or choose another name."
        ]})
        self.assertEqual(Client.objects.count(), 1)

    def test_another_user_cannot_register_the_same_project(self):
        self.login()
        self.create()
        self.login("bob", "bob-pass-123")

        response = self.create()

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"project_id": [OTHER_OWNER_MESSAGE]})

    def test_invalid_input_is_400(self):
        self.login()

        invalid = ({}, {"project_id": "", "name": "n"}, {"project_id": "p", "name": "x" * 256})
        for payload in invalid:
            with self.subTest(payload=payload):
                response = self.http.post(CLIENTS, payload, format="json")
                self.assertEqual(response.status_code, 400)
        self.assertEqual(Client.objects.count(), 0)


class OwnershipTests(UserApiTestCase):
    def setUp(self):
        super().setUp()
        self.bobs, self.bobs_key = create_client(user_id=str(self.bob.pk), project_id="p", name="b")
        self.login()

    def test_list_shows_only_your_clients(self):
        mine = self.create().json()

        ids = [c["id"] for c in self.http.get(CLIENTS).json()]

        self.assertEqual(ids, [mine["id"]])

    def test_someone_elses_client_looks_absent(self):
        responses = [
            self.http.get(detail(self.bobs.id)),
            self.http.delete(detail(self.bobs.id)),
            self.http.post(f"{detail(self.bobs.id)}rotate/"),
        ]

        self.assertEqual([r.status_code for r in responses], [404, 404, 404])
        self.assertEqual(ApiKey.objects.get(client=self.bobs).key_hash, hash_api_key(self.bobs_key))

    def test_unknown_client_is_404(self):
        self.assertEqual(self.http.get(detail("does-not-exist")).status_code, 404)


class RotateAndRevokeTests(UserApiTestCase):
    def setUp(self):
        super().setUp()
        self.login()
        self.created = self.create().json()

    def test_rotate_returns_a_new_key_and_invalidates_the_old_one(self):
        response = self.http.post(f"{detail(self.created['id'])}rotate/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Cache-Control"], "no-store")
        new_key = response.json()["api_key"]
        self.assertNotEqual(new_key, self.created["api_key"])
        self.assertEqual(ApiKey.objects.get().key_hash, hash_api_key(new_key))

    def test_revoke_deletes_the_client_and_its_key(self):
        response = self.http.delete(detail(self.created["id"]))

        self.assertEqual(response.status_code, 204)
        self.assertFalse(Client.objects.exists())
        self.assertFalse(ApiKey.objects.exists())
        self.assertEqual(self.http.get(detail(self.created["id"])).status_code, 404)


@override_settings(CORS_ALLOWED_ORIGINS=["https://contextkit.example"])
class CorsTests(UserApiTestCase):
    ORIGIN = "https://contextkit.example"

    def preflight(self, path, origin):
        return self.client.options(
            path,
            HTTP_ORIGIN=origin,
            HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
            HTTP_ACCESS_CONTROL_REQUEST_HEADERS="authorization,content-type",
        )

    def test_allowed_site_can_call_the_user_api(self):
        response = self.preflight(TOKEN, self.ORIGIN)

        self.assertEqual(response["Access-Control-Allow-Origin"], self.ORIGIN)
        self.assertIn("authorization", response["Access-Control-Allow-Headers"])
        self.assertNotIn("Access-Control-Allow-Credentials", response)

    def test_other_sites_get_no_cors_headers(self):
        response = self.preflight(TOKEN, "https://evil.example")

        self.assertNotIn("Access-Control-Allow-Origin", response)

    def test_cors_is_limited_to_the_user_api(self):
        for path in ("/api/agent/v1/context/briefing/", "/admin/login/"):
            with self.subTest(path=path):
                response = self.preflight(path, self.ORIGIN)
                self.assertNotIn("Access-Control-Allow-Origin", response)


class ProjectOwnershipTests(UserApiTestCase):
    """Only a project's owner may create keys for it (ADR 031, spec A.5)."""

    def setUp(self):
        super().setUp()
        self.login()  # alice, GitHub login "acme"

    def assert_refused(self, response, message):
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.json(), {"project_id": [message]})

    def answer(self, repo=None, error=None):
        self.github.side_effect = error
        self.github.return_value = repo

    def test_owner_creates_a_key_for_their_public_repo(self):
        response = self.create("https://github.com/acme/app")

        self.assertEqual(response.status_code, 201)
        self.github.assert_called_once_with("acme/app")

    def test_repo_owned_by_another_login_is_refused(self):
        self.assert_refused(self.create("https://github.com/someone/app"), NOT_YOUR_REPO_MESSAGE)

    def test_organisation_repo_is_refused(self):
        self.answer(github.GitHubRepoOwner("acme-org", "Organization", False))

        self.assert_refused(self.create("https://github.com/acme-org/app"), NOT_YOUR_REPO_MESSAGE)

    def test_private_or_missing_repo_is_refused(self):
        for repo in (github.GitHubRepoOwner("acme", "User", True), None):
            with self.subTest(repo=repo):
                self.answer(repo)
                response = self.create("https://github.com/acme/app")
                self.assert_refused(response, NOT_YOUR_REPO_MESSAGE)

    def test_github_unreachable_refuses_and_creates_nothing(self):
        self.answer(error=github.GitHubAuthError("down"))

        self.assert_refused(self.create("https://github.com/acme/app"), GITHUB_UNAVAILABLE_MESSAGE)
        self.assertFalse(Client.objects.exists())

    def test_github_sign_in_not_configured_refuses_without_skipping(self):
        with mock.patch.dict("os.environ", {"GITHUB_CLIENT_SECRET": ""}):
            response = self.create("https://github.com/acme/app")

        self.assert_refused(response, NOT_YOUR_REPO_MESSAGE)
        self.github.assert_not_called()

    def test_user_without_a_github_identity_is_refused(self):
        User.objects.create_user("carol", password="carol-pass-123")
        self.login("carol", "carol-pass-123")

        self.assert_refused(self.create("https://github.com/carol/app"), NOT_YOUR_REPO_MESSAGE)
        self.github.assert_not_called()

    def test_non_github_urls_and_folder_paths_are_refused(self):
        for project in ("https://gitlab.com/acme/app", "/Users/acme/app",
                        "https://github.com/acme", "https://github.com/acme/app/tree/main"):
            with self.subTest(project=project):
                self.assert_refused(self.create(project), NOT_YOUR_REPO_MESSAGE)
        self.github.assert_not_called()

    def test_reported_attack_another_account_cannot_take_over_a_project(self):
        # Alice holds acme/app. Bob asks for it, and even if GitHub were fooled into saying
        # Bob owns it, the one-owner rule refuses before GitHub is asked.
        self.assertEqual(self.create("https://github.com/acme/app").status_code, 201)
        self.login("bob", "bob-pass-123")
        self.answer(github.GitHubRepoOwner("bob", "User", False))
        self.github.reset_mock()

        response = self.create("git@github.com:ACME/App.git")

        self.assert_refused(response, OTHER_OWNER_MESSAGE)
        self.github.assert_not_called()
        self.assertEqual(Client.objects.filter(project_id="https://github.com/acme/app").count(), 1)

    def test_every_url_form_of_a_repo_gets_the_same_answer(self):
        forms = ("https://github.com/someone/app", "git@github.com:Someone/App.git",
                 "github.com/SOMEONE/app/", "https://github.com/someone/app.git")
        for form in forms:
            with self.subTest(form=form):
                self.assert_refused(self.create(form), NOT_YOUR_REPO_MESSAGE)
        # The owner's repo in any form is accepted, and recognised as the same project.
        self.assertEqual(self.create("git@github.com:ACME/Tool.git").status_code, 201)
        self.assertEqual(self.create("https://github.com/acme/tool/", name="b").status_code, 201)
        self.assertEqual(
            set(Client.objects.values_list("project_id", flat=True)),
            {"https://github.com/acme/tool"},
        )


class KeysPerAgentTests(UserApiMixin, TransactionTestCase):
    """
    A project has many clients, one per agent, each with its own key (ADR 031, spec B.5).

    TransactionTestCase: core verifies keys through its own read-only connection, which only
    sees committed rows.
    """

    def setUp(self):
        super().setUp()
        self.login()
        self.claude = self.create(name="Claude Code").json()
        self.codex = self.create(name="Codex").json()

    def authenticates(self, key):
        from django.db import connection

        from core.auth import authenticate_client
        from core.errors import AuthenticationError

        with mock.patch.dict("os.environ", {"DJANGO_DB_PATH": connection.settings_dict["NAME"]}):
            try:
                return authenticate_client(key).client_id
            except AuthenticationError:
                return None

    def test_list_returns_every_agent_of_the_project(self):
        listing = self.http.get(CLIENTS).json()

        self.assertEqual({c["name"] for c in listing}, {"Claude Code", "Codex"})
        self.assertEqual({c["project_id"] for c in listing}, {"https://github.com/acme/app"})

    def test_rotating_one_agent_leaves_the_other_working(self):
        rotated = self.http.post(f"{detail(self.claude['id'])}rotate/").json()

        self.assertIsNone(self.authenticates(self.claude["api_key"]))
        self.assertEqual(self.authenticates(rotated["api_key"]), self.claude["id"])
        self.assertEqual(self.authenticates(self.codex["api_key"]), self.codex["id"])

    def test_revoking_one_agent_leaves_the_other_working(self):
        self.http.delete(detail(self.claude["id"]))

        self.assertIsNone(self.authenticates(self.claude["api_key"]))
        self.assertEqual(self.authenticates(self.codex["api_key"]), self.codex["id"])
