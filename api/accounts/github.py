"""GitHub OAuth calls and the public repository list. Standard library only; the client
secret never leaves here."""
import base64
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import NamedTuple, Optional

TOKEN_URL = "https://github.com/login/oauth/access_token"
USER_URL = "https://api.github.com/user"
REPOS_URL = "https://api.github.com/users/{login}/repos"
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


def is_configured() -> bool:
    return bool(os.getenv("GITHUB_CLIENT_ID") and os.getenv("GITHUB_CLIENT_SECRET"))


def _request(request: urllib.request.Request) -> dict:
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise GitHubAuthError("Could not reach GitHub. Try again.") from exc


def exchange_code(code: str, redirect_uri: Optional[str] = None) -> str:
    """Trade the one-time authorization code for a GitHub access token."""
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
