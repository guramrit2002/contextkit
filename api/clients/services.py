"""Issuing clients and API keys. Only the SHA-256 hash of a key is ever stored."""
import hashlib
import secrets

from django.db import transaction

from clients.models import ApiKey, Client

KEY_PREFIX = "ck_"


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


@transaction.atomic
def create_client(*, user_id: str, project_id: str, name: str) -> tuple[Client, str]:
    """Create a client assigned to one project and issue its API key."""
    client = Client(user_id=user_id.strip(), project_id=project_id.strip(), name=name.strip())
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
    return create_client(user_id=owner_id(user), project_id=project_id, name=name)


def rotate_client_key(user, client_id: str) -> tuple[Client, str]:
    client = get_client(user, client_id)
    return client, issue_api_key(client)


def revoke_client(user, client_id: str) -> None:
    """Delete the client and, by cascade, its key. The key stops working immediately."""
    get_client(user, client_id).delete()
