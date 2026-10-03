"""GitHub OAuth calls and the public repository list. Standard library only; the client
secret never leaves here."""
import base64
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import NamedTuple, Optional

from accounts import mock_github

TOKEN_URL = "https://github.com/login/oauth/access_token"
USER_URL = "https://api.github.com/user"
REPOS_URL = "https://api.github.com/users/{login}/repos"
REPO_URL = "https://api.github.com/repos/{owner}/{repo}"
TIMEOUT_SECONDS = 10
REPOS_PER_PAGE = 100
MAX_REPO_PAGES = 3  # at most 300 repositories, most recently pushed first


class GitHubAuthError(Exception):
    """The code could not be exchanged or the user could not be read."""


class GitHubUser(NamedTuple):
    id: int
    login: str


class GitHubRepo(NamedTuple):
    full_name: str
    html_url: str
    pushed_at: Optional[str]
    fork: bool


class GitHubRepoOwner(NamedTuple):
    """Who owns a repository, as GitHub reports it (ADR 031)."""

    login: str
    type: str  # "User" or "Organization"
    private: bool


def is_configured() -> bool:
    if mock_github.enabled():
        return True
    return bool(os.getenv("GITHUB_CLIENT_ID") and os.getenv("GITHUB_CLIENT_SECRET"))


def _request(request: urllib.request.Request) -> dict:
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise GitHubAuthError("Could not reach GitHub. Try again.") from exc


def exchange_code(code: str, redirect_uri: Optional[str] = None) -> str:
    """Trade the one-time authorization code for a GitHub access token."""
    if mock_github.enabled():
        return "mock-token"
    fields = {
        "client_id": os.environ["GITHUB_CLIENT_ID"],
        "client_secret": os.environ["GITHUB_CLIENT_SECRET"],
        "code": code,
    }
    if redirect_uri:
        fields["redirect_uri"] = redirect_uri
    data = _request(urllib.request.Request(
        TOKEN_URL,
        data=urllib.parse.urlencode(fields).encode(),
        headers={"Accept": "application/json"},
        method="POST",
    ))
    token = data.get("access_token")
    if not token:
        # e.g. bad_verification_code: expired, already used, or for another app.
        raise GitHubAuthError("GitHub sign-in failed or expired. Please try again.")
    return token


def fetch_user(access_token: str) -> GitHubUser:
    if mock_github.enabled():
        return GitHubUser(id=mock_github.github_id(), login=mock_github.login())
    data = _request(urllib.request.Request(
        USER_URL,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.github+json",
        },
    ))
    if "id" not in data or "login" not in data:
        raise GitHubAuthError("GitHub did not return a user profile.")
    return GitHubUser(id=int(data["id"]), login=str(data["login"]))


def _app_credentials() -> str:
    # The OAuth app's own credentials as Basic auth: GitHub's higher rate limit for public data,
    # without asking the user for any scope (ADR 030).
    pair = f"{os.environ['GITHUB_CLIENT_ID']}:{os.environ['GITHUB_CLIENT_SECRET']}"
    return "Basic " + base64.b64encode(pair.encode()).decode()


def list_public_repos(login: str) -> list[GitHubRepo]:
    """The user's own public repositories (not organisations'), most recently pushed first."""
    if mock_github.enabled():
        return [
            GitHubRepo(f"{login}/{name}", f"https://github.com/{login}/{name}", None, False)
            for name in mock_github.repo_names()
        ]
    repos: list[GitHubRepo] = []
    for page in range(1, MAX_REPO_PAGES + 1):
        query = urllib.parse.urlencode(
            {"type": "owner", "sort": "pushed", "per_page": REPOS_PER_PAGE, "page": page}
        )
        url = REPOS_URL.format(login=urllib.parse.quote(login, safe="")) + f"?{query}"
        try:
            data = _request(urllib.request.Request(url, headers={
                "Authorization": _app_credentials(),
                "Accept": "application/vnd.github+json",
            }))
        except GitHubAuthError as exc:
            raise GitHubAuthError("Could not load your GitHub repositories.") from exc
        if not isinstance(data, list):
            raise GitHubAuthError("Could not load your GitHub repositories.")
        repos += [
            GitHubRepo(
                full_name=str(item["full_name"]),
                html_url=str(item["html_url"]),
                pushed_at=item.get("pushed_at"),
                fork=bool(item.get("fork")),
            )
            for item in data
            if isinstance(item, dict) and not item.get("private") and "html_url" in item
        ]
        if len(data) < REPOS_PER_PAGE:
            break
    return repos


def fetch_public_repo(full_name: str) -> Optional[GitHubRepoOwner]:
    """
    Look up `owner/repo` with the app's own credentials (no user token, no scope).

    Returns None when GitHub says it doesn't exist; a private repository is also a 404 to app
    credentials. Raises GitHubAuthError when GitHub can't be reached or answers anything else.
    """
    owner, _, repo = full_name.partition("/")
    if mock_github.enabled():
        # The mock login owns its listed repositories; anyone else's repo has its path owner.
        if owner.lower() == mock_github.login().lower():
            names = {name.lower() for name in mock_github.repo_names()}
            return GitHubRepoOwner(owner, "User", False) if repo.lower() in names else None
        return GitHubRepoOwner(owner, "User", False)
    url = REPO_URL.format(
        owner=urllib.parse.quote(owner, safe=""), repo=urllib.parse.quote(repo, safe="")
    )
    try:
        data = _request(urllib.request.Request(url, headers={
            "Authorization": _app_credentials(),
            "Accept": "application/vnd.github+json",
        }))
    except GitHubAuthError as exc:
        cause = exc.__cause__
        if isinstance(cause, urllib.error.HTTPError) and cause.code == 404:
            return None
        raise GitHubAuthError("Could not check the repository on GitHub.") from exc
    owner_data = data.get("owner") if isinstance(data, dict) else None
    if not isinstance(owner_data, dict) or "login" not in owner_data:
        raise GitHubAuthError("GitHub did not return the repository's owner.")
    return GitHubRepoOwner(
        login=str(owner_data["login"]),
        type=str(owner_data.get("type", "")),
        private=bool(data.get("private", True)),
    )
