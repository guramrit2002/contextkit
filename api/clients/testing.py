"""Test helpers: stand-ins for GitHub, so no test ever reaches api.github.com (ADR 031)."""
from unittest import mock

from accounts import github
from accounts.models import GitHubIdentity

GITHUB_CONFIGURED = {"GITHUB_CLIENT_ID": "id", "GITHUB_CLIENT_SECRET": "secret"}


def owned_by_path_owner(full_name: str) -> github.GitHubRepoOwner:
    """Every repository is public and owned by its path's first segment: `acme/app` → acme."""
    return github.GitHubRepoOwner(login=full_name.split("/")[0], type="User", private=False)


def stub_github(test_case, repo=owned_by_path_owner):
    """Configure GitHub sign-in and replace the repository lookup for one test. Returns the mock."""
    for patcher in (
        mock.patch.dict("os.environ", GITHUB_CONFIGURED),
        mock.patch.object(github, "fetch_public_repo", side_effect=repo),
    ):
        started = patcher.start()
        test_case.addCleanup(patcher.stop)
    return started


def link_github(user, login: str, github_id: int) -> GitHubIdentity:
    return GitHubIdentity.objects.create(user=user, github_id=github_id, login=login)
