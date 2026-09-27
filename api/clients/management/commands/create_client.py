import os

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from clients.services import create_client


class Command(BaseCommand):
    help = "Create an API client for one project and print its API key (shown only once)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--project-id",
            required=True,
            help="Git remote URL or folder path, exactly as contextkit identifies the project.",
        )
        parser.add_argument("--name", required=True, help="Human-friendly client name.")
        parser.add_argument(
            "--user-id",
            default=os.getenv("DEFAULT_USER_ID", "default_user"),
            help="Owner of the client (defaults to DEFAULT_USER_ID).",
        )

    def handle(self, *args, **options):
        try:
            client, api_key = create_client(
                user_id=options["user_id"],
                project_id=options["project_id"],
                name=options["name"],
            )
        except ValidationError as exc:
            raise CommandError("; ".join(exc.messages)) from exc

        self.stdout.write(f"Client:  {client.name} ({client.id})")
        self.stdout.write(f"Project: {client.project_id}")
        self.stdout.write(f"API key: {api_key}")
        self.stdout.write(
            self.style.WARNING("Store this key now. It is not saved and cannot be shown again.")
        )
