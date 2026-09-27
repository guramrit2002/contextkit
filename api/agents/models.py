"""Agent identity and API keys. Django is the sole writer; core reads these tables."""
import uuid

from django.db import models


def new_id() -> str:
    # String UUIDs (not UUIDField) so core's SQLAlchemy mapping reads the same value on any DB.
    return str(uuid.uuid4())


class Agent(models.Model):
    id = models.CharField(primary_key=True, max_length=36, default=new_id, editable=False)
    user_id = models.CharField(max_length=255)
    project_id = models.CharField(
        max_length=500,
        help_text="The one project this agent may access: git remote URL or folder path.",
    )
    name = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "agents"
        constraints = [
            models.UniqueConstraint(
                fields=["user_id", "project_id"], name="uniq_agent_user_project"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.project_id})"


class ApiKey(models.Model):
    id = models.CharField(primary_key=True, max_length=36, default=new_id, editable=False)
    agent = models.OneToOneField(Agent, on_delete=models.CASCADE, related_name="api_key")
    key_hash = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "api_keys"

    def __str__(self) -> str:
        return f"key for {self.agent.id}"
