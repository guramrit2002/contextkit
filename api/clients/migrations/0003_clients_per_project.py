"""
A project can have many clients, told apart by name (ADR 031).

Drops the one-client-per-user-per-project rule and makes names unique per project, ignoring
case. Existing rows already satisfy the new rule (at most one client per user and project).
Reversible: going back re-adds the old rule, after checking no project has several clients.
"""
import django.db.models.functions.text
from django.db import migrations, models


def refuse_if_projects_have_several_clients(apps, schema_editor):
    Client = apps.get_model("clients", "Client")
    seen, clashes = set(), []
    for user_id, project_id in Client.objects.values_list("user_id", "project_id"):
        if (user_id, project_id) in seen:
            clashes.append(f"user {user_id}: {project_id}")
        seen.add((user_id, project_id))
    if clashes:
        raise RuntimeError(
            "Can't restore one client per user and project; these have several. Revoke the "
            "extra clients first:\n  " + "\n  ".join(sorted(set(clashes)))
        )


class Migration(migrations.Migration):
    dependencies = [("clients", "0002_normalize_project_ids")]

    operations = [
        migrations.RemoveConstraint(model_name="client", name="uniq_client_user_project"),
        # Runs between the two constraint changes when reversing, before the old rule returns.
        migrations.RunPython(migrations.RunPython.noop, refuse_if_projects_have_several_clients),
        migrations.AddConstraint(
            model_name="client",
            constraint=models.UniqueConstraint(
                django.db.models.functions.text.Lower("name"),
                models.F("user_id"),
                models.F("project_id"),
                name="uniq_client_user_project_name",
            ),
        ),
        migrations.AlterField(
            model_name="client",
            name="project_id",
            field=models.CharField(
                help_text="The project this client works on (canonical repository URL).",
                max_length=500,
            ),
        ),
    ]
