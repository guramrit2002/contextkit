import os

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from agents.services import create_agent


class Command(BaseCommand):
    help = "Create an agent for one project and print its API key (shown only once)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--project-id",
            required=True,
            help="Git remote URL or folder path, exactly as contextkit identifies the project.",
        )
        parser.add_argument("--name", required=True, help="Human-friendly agent name.")
        parser.add_argument(
            "--user-id",
            default=os.getenv("DEFAULT_USER_ID", "default_user"),
            help="Owner of the agent (defaults to DEFAULT_USER_ID).",
        )

    def handle(self, *args, **options):
        try:
            agent, api_key = create_agent(
                user_id=options["user_id"],
                project_id=options["project_id"],
                name=options["name"],
            )
        except ValidationError as exc:
            raise CommandError("; ".join(exc.messages)) from exc

        self.stdout.write(f"Agent:   {agent.name} ({agent.id})")
        self.stdout.write(f"Project: {agent.project_id}")
        self.stdout.write(f"API key: {api_key}")
        self.stdout.write(
            self.style.WARNING("Store this key now. It is not saved and cannot be shown again.")
        )
