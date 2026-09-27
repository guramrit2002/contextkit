"""
Create clients/api_keys (ADR 025).

This app replaces the former `agents` app. On a database that app already migrated, its rows
are carried over, so every existing API key keeps working; on a fresh database the tables are
simply created. Only standard SQL is used, so it runs the same on SQLite and Postgres.
"""
import django.db.models.deletion
from django.db import migrations, models

import clients.models

LEGACY_KEYS = "api_keys_legacy"


def _tables(schema_editor) -> set[str]:
    return set(schema_editor.connection.introspection.table_names())


def set_aside_legacy_keys(apps, schema_editor):
    # The new api_keys table reuses the old name, so move the old one out of the way first.
    if "agents" in _tables(schema_editor):
        q = schema_editor.quote_name
        schema_editor.execute(f"ALTER TABLE {q('api_keys')} RENAME TO {q(LEGACY_KEYS)}")


def carry_over_legacy_rows(apps, schema_editor):
    tables = _tables(schema_editor)
    if "agents" not in tables:
        return
    q = schema_editor.quote_name
    run = schema_editor.execute
    run(
        f"INSERT INTO {q('clients')} (id, user_id, project_id, name, created_at, updated_at) "
        f"SELECT id, user_id, project_id, name, created_at, updated_at FROM {q('agents')}"
    )
    run(
        f"INSERT INTO {q('api_keys')} (id, client_id, key_hash, created_at) "
        f"SELECT id, agent_id, key_hash, created_at FROM {q(LEGACY_KEYS)}"
    )
    run(f"DROP TABLE {q(LEGACY_KEYS)}")
    run(f"DROP TABLE {q('agents')}")

    # Re-point the old app's content types (and their permissions) so admin history and
    # permissions carry over instead of being orphaned.
    if "django_content_type" not in tables:
        return
    ct = q("django_content_type")
    for old_model, new_model in (("agent", "client"), ("apikey", "apikey")):
        # Skip if the new content type already exists; (app_label, model) is unique.
        run(
            f"UPDATE {ct} SET app_label = 'clients', model = '{new_model}' "
            f"WHERE app_label = 'agents' AND model = '{old_model}' AND NOT EXISTS "
            f"(SELECT 1 FROM {ct} WHERE app_label = 'clients' AND model = '{new_model}')"
        )
    if "auth_permission" in tables:
        run(
            f"UPDATE {q('auth_permission')} "
            "SET codename = REPLACE(codename, '_agent', '_client'), "
            "name = REPLACE(name, 'agent', 'client') "
            f"WHERE content_type_id IN (SELECT id FROM {q('django_content_type')} "
            "WHERE app_label = 'clients' AND model = 'client')"
        )


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        migrations.RunPython(set_aside_legacy_keys, migrations.RunPython.noop),
        migrations.CreateModel(
            name="Client",
            fields=[
                (
                    "id",
                    models.CharField(
                        default=clients.models.new_id,
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
                            "The one project this client may access: "
                            "git remote URL or folder path."
                        ),
                        max_length=500,
                    ),
                ),
                ("name", models.CharField(max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"db_table": "clients"},
        ),
        migrations.CreateModel(
            name="ApiKey",
            fields=[
                (
                    "id",
                    models.CharField(
                        default=clients.models.new_id,
                        editable=False,
                        max_length=36,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("key_hash", models.CharField(max_length=64, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "client",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="api_key",
                        to="clients.client",
                    ),
                ),
            ],
            options={"db_table": "api_keys"},
        ),
        migrations.AddConstraint(
            model_name="client",
            constraint=models.UniqueConstraint(
                fields=("user_id", "project_id"), name="uniq_client_user_project"
            ),
        ),
        migrations.RunPython(carry_over_legacy_rows, migrations.RunPython.noop),
    ]
