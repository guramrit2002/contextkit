"""API key holders (clients) and their keys. Django is the sole writer; core reads these tables."""
import uuid

from django.db import models
from django.db.models.functions import Lower


def new_id() -> str:
    # String UUIDs (not UUIDField) so core's SQLAlchemy mapping reads the same value on any DB.
    return str(uuid.uuid4())


class Client(models.Model):
    """
    Anything that holds an API key and calls contextkit over MCP or REST (ADR 025): usually one
    agent working on one project. A project can have many clients, told apart by name (ADR 031).
    """

    id = models.CharField(primary_key=True, max_length=36, default=new_id, editable=False)
    user_id = models.CharField(max_length=255)
    project_id = models.CharField(
        max_length=500,
        help_text="The project this client works on (canonical repository URL).",
    )
    name = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "clients"
        constraints = [
            # One project, many agents; names are unique per project, ignoring case (ADR 031).
            models.UniqueConstraint(
                Lower("name"), "user_id", "project_id", name="uniq_client_user_project_name"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.project_id})"


class ApiKey(models.Model):
    id = models.CharField(primary_key=True, max_length=36, default=new_id, editable=False)
    client = models.OneToOneField(Client, on_delete=models.CASCADE, related_name="api_key")
    key_hash = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "api_keys"

    def __str__(self) -> str:
        return f"key for {self.client.id}"
