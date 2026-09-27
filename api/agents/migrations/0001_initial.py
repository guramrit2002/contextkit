import django.db.models.deletion
from django.db import migrations, models

import agents.models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Agent",
            fields=[
                (
                    "id",
                    models.CharField(
                        default=agents.models.new_id,
                        editable=False,
                        max_length=36,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("user_id", models.CharField(max_length=255)),
                (
                    "project_id",
                    models.CharField(
                        help_text=(
                            "The one project this agent may access: "
                            "git remote URL or folder path."
                        ),
                        max_length=500,
                    ),
                ),
                ("name", models.CharField(max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"db_table": "agents"},
        ),
        migrations.CreateModel(
            name="ApiKey",
            fields=[
                (
                    "id",
                    models.CharField(
                        default=agents.models.new_id,
                        editable=False,
                        max_length=36,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("key_hash", models.CharField(max_length=64, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "agent",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="api_key",
                        to="agents.agent",
                    ),
                ),
            ],
            options={"db_table": "api_keys"},
        ),
        migrations.AddConstraint(
            model_name="agent",
            constraint=models.UniqueConstraint(
                fields=("user_id", "project_id"), name="uniq_agent_user_project"
            ),
        ),
    ]
