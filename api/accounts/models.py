"""Sign-in identities linked to Django users."""
from django.conf import settings
from django.db import models


class GitHubIdentity(models.Model):
    """A GitHub account linked to a Django user, keyed by GitHub's permanent numeric id."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="github"
    )
    # Logins can be renamed on GitHub; the numeric id never changes.
    github_id = models.BigIntegerField(unique=True)
    login = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"{self.login} (GitHub {self.github_id})"
