"""The local GitHub stand-in: works only in DEBUG on SQLite, and never against Postgres."""
from unittest import mock

from django.contrib.auth.models import User
from django.core import checks
from django.test import TestCase, override_settings
from rest_framework.test import APIClient as HttpClient

from accounts import github, mock_github
from accounts.checks import github_mock
from clients.models import Client
from clients.services import NOT_YOUR_REPO_MESSAGE

MOCK = {"GITHUB_MOCK": "true", "GITHUB_CLIENT_ID": "", "GITHUB_CLIENT_SECRET": ""}
AUTHORIZE = "/api/v1/auth/github/mock-authorize/"


@override_settings(DEBUG=True)
@mock.patch.dict("os.environ", MOCK)
class MockEnabledTests(TestCase):
    def setUp(self):
        self.http = HttpClient()

    def sign_in(self):
        access = self.http.post("/api/v1/auth/github/", {"code": "mock"}, format="json").json()
        self.http.credentials(HTTP_AUTHORIZATION=f"Bearer {access['access']}")

    def test_github_calls_are_answered_locally(self):
        with mock.patch("urllib.request.urlopen") as network:
            self.assertTrue(github.is_configured())
            self.assertEqual(github.fetch_user(github.exchange_code("x")).login, "mock-user")
            names = [r.full_name for r in github.list_public_repos("mock-user")]
            self.assertEqual(names, ["mock-user/contextkit", "mock-user/demo-app"])
        network.assert_not_called()

    def test_sign_in_creates_the_mock_user(self):
        self.sign_in()

        self.assertEqual(User.objects.get().github.login, "mock-user")

    def test_keys_for_mock_repos_work_and_other_repos_are_refused(self):
        self.sign_in()

        ok = self.http.post("/api/v1/clients/", {
            "project_id": "https://github.com/mock-user/contextkit", "name": "Claude Code",
        }, format="json")
        missing = self.http.post("/api/v1/clients/", {
            "project_id": "https://github.com/mock-user/not-listed", "name": "x",
        }, format="json")
        theirs = self.http.post("/api/v1/clients/", {
            "project_id": "https://github.com/someone/contextkit", "name": "x",
        }, format="json")

        self.assertEqual(ok.status_code, 201)
        for response in (missing, theirs):
            self.assertEqual(response.json(), {"project_id": [NOT_YOUR_REPO_MESSAGE]})
        self.assertEqual(Client.objects.count(), 1)

    def test_login_and_repos_can_be_configured(self):
        env = {"GITHUB_MOCK_LOGIN": "dev", "GITHUB_MOCK_REPOS": " a , b ", "GITHUB_MOCK_ID": "7"}
        with mock.patch.dict("os.environ", env):
            self.assertEqual(github.fetch_user("t"), github.GitHubUser(7, "dev"))
            self.assertEqual([r.full_name for r in github.list_public_repos("dev")],
                             ["dev/a", "dev/b"])

    def test_authorize_page_sends_the_browser_back_with_a_code(self):
        response = self.http.get(AUTHORIZE, {
            "redirect_uri": "http://localhost:5180/", "state": "abc", "client_id": "x",
        })

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "http://localhost:5180/?code=mock&state=abc")

    def test_authorize_page_only_returns_to_this_machine(self):
        for params in ({"redirect_uri": "https://evil.example/", "state": "s"},
                       {"redirect_uri": "http://localhost:5180/"}):
            with self.subTest(params=params):
                self.assertEqual(self.http.get(AUTHORIZE, params).status_code, 400)

    def test_startup_check_reports_the_mock(self):
        [message] = github_mock(None)

        self.assertEqual((message.level, message.id), (checks.INFO, "accounts.I001"))


@mock.patch.dict("os.environ", MOCK)
class MockRefusedTests(TestCase):
    def test_off_without_debug(self):
        with override_settings(DEBUG=False):
            self.assertFalse(mock_github.enabled())
            [warning] = github_mock(None)
            self.assertEqual(warning.id, "accounts.W001")
            self.assertEqual(HttpClient().get(AUTHORIZE).status_code, 404)

    def test_never_on_postgres(self):
        with override_settings(DEBUG=True), \
                mock.patch.object(mock_github.connection, "vendor", "postgresql"):
            self.assertFalse(mock_github.enabled())
            self.assertFalse(github.is_configured())
            [error] = github_mock(None)
            self.assertEqual((error.level, error.id), (checks.ERROR, "accounts.E001"))

    def test_off_unless_requested(self):
        with override_settings(DEBUG=True), mock.patch.dict("os.environ", {"GITHUB_MOCK": ""}):
            self.assertFalse(mock_github.enabled())
            self.assertEqual(github_mock(None), [])
