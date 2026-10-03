"""GitHub sign-in (ADR 028) and the repository picker (ADR 030). GitHub itself is mocked."""
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
        repo = github.GitHubRepoOwner(login="octocat", type="User", private=False)
        with mock.patch.object(github, "fetch_public_repo", return_value=repo):
            created = self.http.post(
                "/api/v1/clients/", {"project_id": "https://github.com/octocat/r", "name": "n"},
                format="json",
            )

        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["project_id"], "https://github.com/octocat/r")

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


def repo(name, private=False, fork=False, pushed="2026-09-01T00:00:00Z"):
    return {
        "full_name": f"octocat/{name}", "html_url": f"https://github.com/octocat/{name}",
        "private": private, "fork": fork, "pushed_at": pushed,
    }


class GitHubRepoListingTests(TestCase):
    """The HTTP layer for GET /users/{login}/repos."""

    def pages(self, *pages):
        responses = []
        for payload in pages:
            response = mock.MagicMock()
            response.__enter__.return_value.read.return_value = __import__("json").dumps(
                payload
            ).encode()
            responses.append(response)
        return mock.patch("urllib.request.urlopen", side_effect=responses)

    @mock.patch.dict("os.environ", CONFIGURED)
    def test_lists_public_repos_with_app_credentials_and_no_user_token(self):
        with self.pages([repo("App"), repo("secret", private=True)]) as urlopen:
            repos = github.list_public_repos("octocat")

        self.assertEqual([r.full_name for r in repos], ["octocat/App"])
        request = urlopen.call_args.args[0]
        self.assertTrue(request.full_url.startswith("https://api.github.com/users/octocat/repos?"))
        self.assertIn("type=owner", request.full_url)
        self.assertIn("sort=pushed", request.full_url)
        # Basic auth with the app's id:secret ("id:secret" base64), not a user token.
        self.assertEqual(request.headers["Authorization"], "Basic aWQ6c2VjcmV0")

    @mock.patch.dict("os.environ", CONFIGURED)
    def test_follows_pages_until_a_short_one(self):
        full = [repo(f"r{i}") for i in range(github.REPOS_PER_PAGE)]
        with self.pages(full, [repo("last")]) as urlopen:
            repos = github.list_public_repos("octocat")

        self.assertEqual(len(repos), github.REPOS_PER_PAGE + 1)
        self.assertEqual(urlopen.call_count, 2)

    @mock.patch.dict("os.environ", CONFIGURED)
    def test_stops_after_the_page_limit(self):
        full = [repo(f"r{i}") for i in range(github.REPOS_PER_PAGE)]
        with self.pages(*[full] * (github.MAX_REPO_PAGES + 1)) as urlopen:
            github.list_public_repos("octocat")

        self.assertEqual(urlopen.call_count, github.MAX_REPO_PAGES)

    @mock.patch.dict("os.environ", CONFIGURED)
    def test_unexpected_answer_or_unreachable_github_raises_a_clean_error(self):
        with self.pages({"message": "Not Found"}), self.assertRaises(github.GitHubAuthError):
            github.list_public_repos("ghost")
        with mock.patch("urllib.request.urlopen", side_effect=TimeoutError()), \
                self.assertRaisesMessage(github.GitHubAuthError, "Could not load"):
            github.list_public_repos("octocat")


REPOS = "/api/v1/github/repos/"


class GitHubReposEndpointTests(TestCase):
    def setUp(self):
        cache.clear()
        self.http = HttpClient()
        env = mock.patch.dict("os.environ", CONFIGURED)
        env.start()
        self.addCleanup(env.stop)

    def sign_in(self, gh_user=github.GitHubUser(101, "octocat")):
        with mock.patch.object(github, "exchange_code", return_value="gh-token"), \
                mock.patch.object(github, "fetch_user", return_value=gh_user):
            access = self.http.post(URL, {"code": "c"}, format="json").json()["access"]
        self.http.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

    def listing(self, repos):
        return mock.patch.object(github, "list_public_repos", return_value=repos)

    def test_needs_a_jwt(self):
        self.assertEqual(self.http.get(REPOS).status_code, 401)

    def test_returns_repos_with_their_canonical_project_id(self):
        self.sign_in()
        repos = [
            github.GitHubRepo("octocat/App", "https://github.com/octocat/App", "2026-09-01", True)
        ]

        with self.listing(repos) as listed:
            response = self.http.get(REPOS)

        listed.assert_called_once_with("octocat")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {
            "login": "octocat",
            "repositories": [{
                "full_name": "octocat/App", "project_id": "https://github.com/octocat/app",
                "pushed_at": "2026-09-01", "fork": True,
            }],
        })

    def test_listing_is_cached_per_user(self):
        self.sign_in()

        with self.listing([]) as listed:
            self.http.get(REPOS)
            self.http.get(REPOS)

        self.assertEqual(listed.call_count, 1)

    def test_password_users_get_an_empty_list(self):
        User.objects.create_user("plain", password="plain-pass-123")
        access = self.http.post(
            "/api/v1/auth/token/", {"username": "plain", "password": "plain-pass-123"},
            format="json",
        ).json()["access"]
        self.http.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

        with self.listing([]) as listed:
            response = self.http.get(REPOS)

        listed.assert_not_called()
        self.assertEqual(response.json(), {"login": None, "repositories": []})

    def test_github_failure_is_502(self):
        self.sign_in()

        with mock.patch.object(
            github, "list_public_repos",
            side_effect=github.GitHubAuthError("Could not load your GitHub repositories."),
        ):
            response = self.http.get(REPOS)

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["detail"], "Could not load your GitHub repositories.")

    def test_not_configured_is_503(self):
        self.sign_in()

        with mock.patch.dict("os.environ", {"GITHUB_CLIENT_SECRET": ""}):
            self.assertEqual(self.http.get(REPOS).status_code, 503)


class FetchPublicRepoTests(TestCase):
    """GET /repos/{owner}/{repo} with app credentials (ADR 031)."""

    def respond(self, payload):
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = __import__("json").dumps(
            payload
        ).encode()
        return mock.patch("urllib.request.urlopen", return_value=response)

    def http_error(self, code):
        import urllib.error

        return mock.patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.HTTPError("u", code, "msg", {}, None),
        )

    @mock.patch.dict("os.environ", CONFIGURED)
    def test_public_repo_returns_its_owner(self):
        body = {"private": False, "owner": {"login": "Octocat", "type": "User"}}
        with self.respond(body) as urlopen:
            repo = github.fetch_public_repo("octocat/hello")

        self.assertEqual(repo, github.GitHubRepoOwner("Octocat", "User", False))
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.github.com/repos/octocat/hello")
        self.assertEqual(request.headers["Authorization"], "Basic aWQ6c2VjcmV0")

    @mock.patch.dict("os.environ", CONFIGURED)
    def test_organisation_and_private_flags_are_reported(self):
        body = {"private": True, "owner": {"login": "acme", "type": "Organization"}}
        with self.respond(body):
            repo = github.fetch_public_repo("acme/app")

        self.assertEqual((repo.type, repo.private), ("Organization", True))

    @mock.patch.dict("os.environ", CONFIGURED)
    def test_404_returns_none(self):
        with self.http_error(404):
            self.assertIsNone(github.fetch_public_repo("ghost/nothing"))

    @mock.patch.dict("os.environ", CONFIGURED)
    def test_other_errors_and_network_failures_raise(self):
        for failure in (self.http_error(500), self.http_error(403),
                        mock.patch("urllib.request.urlopen", side_effect=TimeoutError())):
            with self.subTest(failure=failure), failure, \
                    self.assertRaises(github.GitHubAuthError):
                github.fetch_public_repo("octocat/hello")

    @mock.patch.dict("os.environ", CONFIGURED)
    def test_answer_without_an_owner_raises(self):
        with self.respond({"private": False}), self.assertRaises(github.GitHubAuthError):
            github.fetch_public_repo("octocat/hello")
