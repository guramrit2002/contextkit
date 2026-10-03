"""Revoke a user's API keys when the user is deleted (see services.revoke_all_for_user)."""
from django.conf import settings
from django.db.models.signals import pre_delete
from django.dispatch import receiver

from clients import services


@receiver(pre_delete, sender=settings.AUTH_USER_MODEL, dispatch_uid="clients.revoke_on_user_delete")
def revoke_keys_of_deleted_user(sender, instance, **kwargs):
    # pre_delete runs inside the deletion's transaction: if the user isn't deleted after all,
    # their keys aren't either.
    services.revoke_all_for_user(str(instance.pk))
