"""GitHub sign-in (link or create the Django user, issue our own JWTs) and repo listing."""
import os

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import transaction
from rest_framework_simplejwt.tokens import RefreshToken

from accounts import github
from accounts.models import GitHubIdentity
from core.projects import normalize_project_id

REPOS_CACHE_SECONDS = 300


class SignInNotAllowed(Exception):
    """The GitHub account is valid but not on GITHUB_ALLOWED_LOGINS."""


def allowed_logins() -> set[str]:
    raw = os.getenv("GITHUB_ALLOWED_LOGINS", "")
    return {login.strip().lower() for login in raw.split(",") if login.strip()}


def _unique_username(login: str, github_id: int) -> str:
    User = get_user_model()
    return login if not User.objects.filter(username=login).exists() else f"{login}-gh{github_id}"


@transaction.atomic
def user_for(gh: github.GitHubUser):
    """The Django user linked to this GitHub account, created on first sign-in."""
    identity = GitHubIdentity.objects.select_related("user").filter(github_id=gh.id).first()
    if identity:
        if identity.login != gh.login:
            identity.login = gh.login  # renamed on GitHub; the id still matches
            identity.save(update_fields=["login", "updated_at"])
        return identity.user

    User = get_user_model()
    user = User(username=_unique_username(gh.login, gh.id))
    user.set_unusable_password()  # GitHub accounts never sign in with a password
    user.save()
    GitHubIdentity.objects.create(user=user, github_id=gh.id, login=gh.login)
    return user


def sign_in_with_github(code: str, redirect_uri: str | None = None) -> dict:
    """Exchange the OAuth code and return our JWT pair plus the GitHub login."""
    gh = github.fetch_user(github.exchange_code(code, redirect_uri))
    allowed = allowed_logins()
    if allowed and gh.login.lower() not in allowed:
        raise SignInNotAllowed(f"GitHub user {gh.login} is not allowed to sign in.")
    user = user_for(gh)
    refresh = RefreshToken.for_user(user)
    return {"access": str(refresh.access_token), "refresh": str(refresh), "login": gh.login}


def github_repositories(user) -> dict:
    """
    The signed-in user's public GitHub repositories, for the website's repository picker.

    Each comes with the canonical project ID a key for it would be stored under. Users who
    didn't sign in with GitHub get an empty list.
    """
    identity = GitHubIdentity.objects.filter(user=user).first()
    if identity is None:
        return {"login": None, "repositories": []}

    cache_key = f"github-repos:{identity.github_id}:{identity.login}"
    repositories = cache.get(cache_key)
    if repositories is None:
        repositories = [
            {
                "full_name": repo.full_name,
                "project_id": normalize_project_id(repo.html_url),
                "pushed_at": repo.pushed_at,
                "fork": repo.fork,
            }
            for repo in github.list_public_repos(identity.login)
        ]
        cache.set(cache_key, repositories, REPOS_CACHE_SECONDS)
    return {"login": identity.login, "repositories": repositories}
