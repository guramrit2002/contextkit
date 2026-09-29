"""GitHub sign-in (ADR 028). GitHub itself is mocked at the two network calls."""
from unittest import mock

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient as HttpClient

from accounts import github
from accounts.models import GitHubIdentity

URL = "/api/v1/auth/github/"
CONFIGURED = {"GITHUB_CLIENT_ID": "id", "GITHUB_CLIENT_SECRET": "secret"}


class GitHubSignInTests(TestCase):
    def setUp(self):
        cache.clear()
        self.http = HttpClient()
        env = mock.patch.dict("os.environ", CONFIGURED)
        env.start()
        self.addCleanup(env.stop)

    def sign_in(self, gh_user=github.GitHubUser(101, "octocat"), code="good-code", **extra):
        with mock.patch.object(github, "exchange_code", return_value="gh-token") as exchange, \
                mock.patch.object(github, "fetch_user", return_value=gh_user):
            response = self.http.post(URL, {"code": code, **extra}, format="json")
        self.exchange = exchange
        return response

    def test_first_sign_in_creates_a_linked_user_and_returns_jwts(self):
        response = self.sign_in()

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(set(body), {"access", "refresh", "login"})
        self.assertEqual(body["login"], "octocat")
        self.assertEqual(response["Cache-Control"], "no-store")
        user = User.objects.get()
        self.assertEqual(user.username, "octocat")
        self.assertFalse(user.has_usable_password())
        self.assertEqual(user.github.github_id, 101)

    def test_the_jwt_works_on_the_key_endpoints(self):
        access = self.sign_in().json()["access"]

        self.http.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        created = self.http.post(
            "/api/v1/clients/", {"project_id": "https://github.com/o/r", "name": "n"},
            format="json",
        )

        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["project_id"], "https://github.com/o/r")

    def test_returning_user_is_matched_by_github_id_even_after_a_rename(self):
        self.sign_in()

        self.sign_in(github.GitHubUser(101, "octo-renamed"))

        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(GitHubIdentity.objects.get().login, "octo-renamed")

    def test_username_clash_gets_a_unique_name(self):
        User.objects.create_user("octocat", password="x")

        self.sign_in()

        self.assertTrue(User.objects.filter(username="octocat-gh101").exists())

    def test_redirect_uri_is_passed_to_github(self):
        self.sign_in(redirect_uri="https://contextkit.example/")

        self.exchange.assert_called_once_with("good-code", "https://contextkit.example/")

    def test_rejected_code_is_400_without_creating_a_user(self):
        with mock.patch.object(
            github, "exchange_code", side_effect=github.GitHubAuthError("GitHub sign-in failed")
        ):
            response = self.http.post(URL, {"code": "bad"}, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertIn("GitHub sign-in failed", response.json()["detail"])
        self.assertFalse(User.objects.exists())

    def test_allowlist_blocks_other_accounts(self):
        with mock.patch.dict("os.environ", {"GITHUB_ALLOWED_LOGINS": "Alice, bob"}):
            denied = self.sign_in()
            allowed = self.sign_in(github.GitHubUser(7, "alice"))

        self.assertEqual(denied.status_code, 403)
        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(list(User.objects.values_list("username", flat=True)), ["alice"])

    def test_not_configured_is_503(self):
        with mock.patch.dict("os.environ", {"GITHUB_CLIENT_SECRET": ""}):
            response = self.http.post(URL, {"code": "x"}, format="json")

        self.assertEqual(response.status_code, 503)

    def test_missing_code_is_400(self):
        self.assertEqual(self.http.post(URL, {}, format="json").status_code, 400)

    def test_sign_in_is_throttled_with_login(self):
        codes = [self.sign_in(code=f"c{i}").status_code for i in range(11)]

        self.assertEqual(codes, [200] * 10 + [429])


class GitHubClientTests(TestCase):
    """The HTTP layer: what we send to GitHub and how its answers are read."""

    def respond(self, payload):
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = __import__("json").dumps(
            payload
        ).encode()
        return mock.patch("urllib.request.urlopen", return_value=response)

    @mock.patch.dict("os.environ", CONFIGURED)
    def test_exchange_sends_secret_and_code_and_returns_the_token(self):
        with self.respond({"access_token": "gho_x"}) as urlopen:
            token = github.exchange_code("the-code", "https://site.example/")

        request = urlopen.call_args.args[0]
        self.assertEqual(token, "gho_x")
        self.assertEqual(request.full_url, github.TOKEN_URL)
        self.assertIn(b"client_secret=secret", request.data)
        self.assertIn(b"code=the-code", request.data)
        self.assertIn(b"redirect_uri=https%3A%2F%2Fsite.example%2F", request.data)

    @mock.patch.dict("os.environ", CONFIGURED)
    def test_github_error_answer_raises(self):
        with self.respond({"error": "bad_verification_code"}):
            with self.assertRaises(github.GitHubAuthError):
                github.exchange_code("expired")

    def test_fetch_user_reads_id_and_login(self):
        with self.respond({"id": 42, "login": "hubot", "name": "ignored"}) as urlopen:
            user = github.fetch_user("gho_x")

        self.assertEqual(user, github.GitHubUser(42, "hubot"))
        self.assertEqual(urlopen.call_args.args[0].headers["Authorization"], "Bearer gho_x")

    def test_unreachable_github_raises_a_clean_error(self):
        with mock.patch("urllib.request.urlopen", side_effect=TimeoutError()):
            with self.assertRaises(github.GitHubAuthError):
                github.fetch_user("gho_x")
