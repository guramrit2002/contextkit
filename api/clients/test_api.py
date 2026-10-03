"""User API (ADR 028): JWT login and API-key management."""
from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient as HttpClient

from clients.models import ApiKey, Client
from clients.services import KEY_PREFIX, create_client, hash_api_key

TOKEN = "/api/v1/auth/token/"
REFRESH = "/api/v1/auth/token/refresh/"
CLIENTS = "/api/v1/clients/"


def detail(client_id):
    return f"{CLIENTS}{client_id}/"


class UserApiTestCase(TestCase):
    def setUp(self):
        cache.clear()  # throttle counters live in the cache
        self.alice = User.objects.create_user("alice", password="alice-pass-123")
        self.bob = User.objects.create_user("bob", password="bob-pass-123")
        self.http = HttpClient()

    def login(self, username="alice", password="alice-pass-123"):
        credentials = {"username": username, "password": password}
        response = self.http.post(TOKEN, credentials, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.http.credentials(HTTP_AUTHORIZATION=f"Bearer {response.json()['access']}")
        return response.json()

    def create(self, project_id="https://github.com/acme/app", name="laptop"):
        return self.http.post(CLIENTS, {"project_id": project_id, "name": name}, format="json")


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

    def test_one_client_per_user_and_project(self):
        self.login()
        self.create(name="first")

        response = self.create(name="second")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Client.objects.count(), 1)

    def test_create_stores_and_returns_the_canonical_project_id(self):
        self.login()

        response = self.create(project_id="git@github.com:Acme/App.git")

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["project_id"], "https://github.com/acme/app")
        self.assertEqual(Client.objects.get().project_id, "https://github.com/acme/app")

    def test_another_form_of_the_same_repository_says_rotate_instead(self):
        self.login()
        self.create(project_id="https://github.com/acme/app")

        response = self.create(project_id="git@github.com:acme/app.git", name="second")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json(),
            {"project_id": ["You already have a key for this repository. Rotate it instead."]},
        )
        self.assertEqual(Client.objects.count(), 1)

    def test_other_users_can_use_the_same_project(self):
        self.login()
        self.create()
        self.login("bob", "bob-pass-123")

        self.assertEqual(self.create().status_code, 201)

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
