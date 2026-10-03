"""Deleting a user revokes their API keys (clients.user_id has no foreign key to cascade)."""
from unittest import mock

from django.contrib.auth.models import User
from django.core import checks
from django.db import connection
from django.test import TestCase, TransactionTestCase
from django.urls import reverse

from clients.checks import orphaned_client_keys
from clients.models import ApiKey, Client
from clients.services import create_client, orphaned_clients, revoke_all_for_user
from core.auth import authenticate_client
from core.errors import AuthenticationError


def owned_by(user, project="https://github.com/o/r", name="laptop"):
    return create_client(user_id=str(user.pk), project_id=project, name=name)


class RevokeOnDeleteTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user("alice")
        self.bob = User.objects.create_user("bob")

    def test_deleting_a_user_deletes_their_clients_and_keys(self):
        owned_by(self.alice, "https://github.com/a/one")
        owned_by(self.alice, "https://github.com/a/two")
        bobs, _ = owned_by(self.bob)

        self.alice.delete()

        self.assertEqual(list(Client.objects.values_list("id", flat=True)), [bobs.id])
        self.assertEqual(ApiKey.objects.count(), 1)

    def test_bulk_delete_also_revokes(self):
        owned_by(self.alice)
        owned_by(self.bob)

        User.objects.filter(username__in=["alice", "bob"]).delete()

        self.assertFalse(Client.objects.exists())
        self.assertFalse(ApiKey.objects.exists())

    def test_deleting_a_user_in_the_admin_revokes_their_keys(self):
        admin = User.objects.create_superuser("admin", "admin@example.com", "pw")
        self.client.force_login(admin)
        owned_by(self.alice)

        response = self.client.post(
            reverse("admin:auth_user_delete", args=[self.alice.pk]), {"post": "yes"}
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(Client.objects.filter(user_id=str(self.alice.pk)).exists())

    def test_revoke_all_for_user_counts_clients(self):
        owned_by(self.alice, "https://github.com/a/one")
        owned_by(self.alice, "https://github.com/a/two")

        self.assertEqual(revoke_all_for_user(str(self.alice.pk)), 2)
        self.assertEqual(revoke_all_for_user(str(self.alice.pk)), 0)


class OrphanedClientsCheckTests(TestCase):
    def test_lists_clients_of_users_that_no_longer_exist(self):
        alice = User.objects.create_user("alice")
        owned_by(alice)
        orphan, _ = create_client(user_id="999", project_id="https://github.com/x/y", name="old")

        self.assertEqual([c.id for c in orphaned_clients()], [orphan.id])
        [warning] = orphaned_client_keys(None, databases=["default"])
        self.assertEqual(warning.id, "clients.W001")
        self.assertIn(orphan.id, warning.msg)
        self.assertIn("still work", warning.msg)

    def test_no_warning_without_orphans_or_outside_database_checks(self):
        create_client(user_id="999", project_id="https://github.com/x/y", name="old")

        self.assertEqual(orphaned_client_keys(None, databases=None), [])
        Client.objects.all().delete()
        self.assertEqual(orphaned_client_keys(None, databases=["default"]), [])

    def test_check_is_registered_for_database_checks(self):
        create_client(user_id="999", project_id="https://github.com/x/y", name="old")

        ids = [m.id for m in checks.run_checks(tags=[checks.Tags.database], databases=["default"])]
        self.assertIn("clients.W001", ids)


class DeletedUsersKeyIsRejectedTests(TransactionTestCase):
    """End to end: core, which verifies keys for the MCP server, refuses the deleted user's key."""

    def test_key_stops_working_when_its_user_is_deleted(self):
        alice = User.objects.create_user("alice")
        _, key = owned_by(alice)
        db = {"DJANGO_DB_PATH": connection.settings_dict["NAME"]}

        with mock.patch.dict("os.environ", db):
            self.assertEqual(authenticate_client(key).user_id, str(alice.pk))
            alice.delete()
            with self.assertRaisesMessage(AuthenticationError, "Invalid API key"):
                authenticate_client(key)
