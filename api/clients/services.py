"""Issuing clients and API keys. Only the SHA-256 hash of a key is ever stored."""
import hashlib
import secrets
from urllib.parse import urlsplit

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction

from accounts import github
from accounts.models import GitHubIdentity
from clients.models import ApiKey, Client
from core.projects import normalize_project_id

KEY_PREFIX = "ck_"
DUPLICATE_PROJECT_MESSAGE = "You already have a key for this repository. Rotate it instead."
OTHER_OWNER_MESSAGE = "This repository is registered to another account."
NOT_YOUR_REPO_MESSAGE = "You can only create keys for public repositories you own on GitHub."
GITHUB_UNAVAILABLE_MESSAGE = "Could not check the repository on GitHub. Try again."


def hash_api_key(api_key: str) -> str:
    # Must stay identical to core.auth.hash_api_key, which verifies keys on every request.
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def generate_api_key() -> str:
    return KEY_PREFIX + secrets.token_urlsafe(32)


@transaction.atomic
def issue_api_key(client: Client) -> str:
    """Create a new key for the client, replacing any existing one. Returns the plaintext key."""
    api_key = generate_api_key()
    ApiKey.objects.filter(client=client).delete()
    ApiKey.objects.create(client=client, key_hash=hash_api_key(api_key))
    return api_key


def canonical_project_id(project_id: str) -> str:
    """The project ID as core stores and compares it (ADR 030), or a Django ValidationError."""
    try:
        return normalize_project_id(project_id)
    except ValueError as exc:
        raise ValidationError({"project_id": [str(exc)]}) from exc


def ensure_single_owner(user_id: str, project_id: str) -> None:
    """A project has one owner: whoever already holds its clients (ADR 031)."""
    if Client.objects.filter(project_id=project_id).exclude(user_id=user_id).exists():
        # Never say who: that would reveal another account's repositories.
        raise ValidationError({"project_id": [OTHER_OWNER_MESSAGE]})


def _not_yours() -> ValidationError:
    return ValidationError({"project_id": [NOT_YOUR_REPO_MESSAGE]})


def ensure_owns_on_github(user, project_id: str) -> None:
    """
    The user must own the repository on GitHub, and it must be public (ADR 031).

    Fails closed: anything that can't be proven, including a non-GitHub project, an unlinked
    account, GitHub sign-in not configured or GitHub unreachable, refuses the key.
    """
    parts = urlsplit(project_id)
    segments = [s for s in parts.path.split("/") if s]
    if parts.scheme != "https" or parts.hostname != "github.com" or len(segments) != 2:
        raise _not_yours()
    identity = GitHubIdentity.objects.filter(user=user).first()
    if identity is None or not github.is_configured():
        raise _not_yours()
    try:
        repo = github.fetch_public_repo("/".join(segments))
    except github.GitHubAuthError as exc:
        raise ValidationError({"project_id": [GITHUB_UNAVAILABLE_MESSAGE]}) from exc
    # An organisation's login never equals a user's, so organisation repos are refused too.
    if repo is None or repo.private or repo.login.lower() != identity.login.lower():
        raise _not_yours()


@transaction.atomic
def create_client(*, user_id: str, project_id: str, name: str) -> tuple[Client, str]:
    """
    Create a client assigned to one project and issue its API key.

    Also the trusted operator path (admin, manage.py create_client): it skips the GitHub check
    but keeps the one-owner rule.
    """
    user_id, project_id = user_id.strip(), canonical_project_id(project_id)
    ensure_single_owner(user_id, project_id)
    if Client.objects.filter(user_id=user_id, project_id=project_id).exists():
        # Any URL form of a repository is the same project, and each has one key (ADR 022).
        raise ValidationError({"project_id": [DUPLICATE_PROJECT_MESSAGE]})
    client = Client(user_id=user_id, project_id=project_id, name=name.strip())
    client.full_clean()
    client.save()
    return client, issue_api_key(client)


def owner_id(user) -> str:
    """The user_id stored on a client: the Django user's primary key, as a string."""
    return str(user.pk)


def list_clients(user) -> list[Client]:
    return list(
        Client.objects.filter(user_id=owner_id(user))
        .select_related("api_key")
        .order_by("-created_at")
    )


def get_client(user, client_id: str) -> Client:
    """The user's own client. Raises Client.DoesNotExist for anyone else's, so it looks absent."""
    return Client.objects.select_related("api_key").get(id=client_id, user_id=owner_id(user))


def create_client_for_user(user, *, project_id: str, name: str) -> tuple[Client, str]:
    """The user API and website: only the project's owner, proven on GitHub (ADR 031)."""
    user_id, project_id = owner_id(user), canonical_project_id(project_id)
    ensure_single_owner(user_id, project_id)
    # Outside the database transaction: a slow GitHub must not hold one open.
    ensure_owns_on_github(user, project_id)
    return create_client(user_id=user_id, project_id=project_id, name=name)


def rotate_client_key(user, client_id: str) -> tuple[Client, str]:
    client = get_client(user, client_id)
    return client, issue_api_key(client)


def revoke_client(user, client_id: str) -> None:
    """Delete the client and, by cascade, its key. The key stops working immediately."""
    get_client(user, client_id).delete()


def revoke_all_for_user(user_id: str) -> int:
    """
    Delete every client of a user and, by cascade, their keys. Returns how many were deleted.

    clients.user_id is a plain string (core reads it without Django), so the database can't
    cascade a user's deletion to their clients; this does it instead.
    """
    _, per_model = Client.objects.filter(user_id=str(user_id)).delete()
    return per_model.get(Client._meta.label, 0)


def orphaned_clients() -> list[Client]:
    """Clients whose user no longer exists. Their keys still work until revoked."""
    user_ids = {str(pk) for pk in get_user_model().objects.values_list("pk", flat=True)}
    return [c for c in Client.objects.order_by("created_at") if c.user_id not in user_ids]


def shared_projects() -> dict[str, list[Client]]:
    """Projects whose clients belong to more than one user, with those clients (ADR 031)."""
    by_project: dict[str, list[Client]] = {}
    for client in Client.objects.order_by("project_id", "created_at"):
        by_project.setdefault(client.project_id, []).append(client)
    return {
        project_id: clients
        for project_id, clients in by_project.items()
        if len({c.user_id for c in clients}) > 1
    }
