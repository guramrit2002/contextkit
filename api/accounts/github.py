"""The two GitHub OAuth calls. Standard library only; the client secret never leaves here."""
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import NamedTuple, Optional

TOKEN_URL = "https://github.com/login/oauth/access_token"
USER_URL = "https://api.github.com/user"
TIMEOUT_SECONDS = 10


class GitHubAuthError(Exception):
    """The code could not be exchanged or the user could not be read."""


class GitHubUser(NamedTuple):
    id: int
    login: str


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
