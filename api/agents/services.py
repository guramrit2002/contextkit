"""Issuing agents and API keys. Only the SHA-256 hash of a key is ever stored."""
import hashlib
import secrets

from django.db import transaction

from agents.models import Agent, ApiKey

KEY_PREFIX = "ck_"


def hash_api_key(api_key: str) -> str:
    # Must stay identical to core.auth.hash_api_key, which verifies keys on the agent path.
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def generate_api_key() -> str:
    return KEY_PREFIX + secrets.token_urlsafe(32)


@transaction.atomic
def issue_api_key(agent: Agent) -> str:
    """Create a new key for the agent, replacing any existing one. Returns the plaintext key."""
    api_key = generate_api_key()
    ApiKey.objects.filter(agent=agent).delete()
    ApiKey.objects.create(agent=agent, key_hash=hash_api_key(api_key))
    return api_key


@transaction.atomic
def create_agent(*, user_id: str, project_id: str, name: str) -> tuple[Agent, str]:
    """Create an agent assigned to one project and issue its API key."""
    agent = Agent(user_id=user_id.strip(), project_id=project_id.strip(), name=name.strip())
    agent.full_clean()
    agent.save()
    return agent, issue_api_key(agent)
