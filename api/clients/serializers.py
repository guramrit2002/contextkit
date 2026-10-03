"""Request and response shapes for the user API-key endpoints."""
from rest_framework import serializers

from clients.models import Client


class CreateClientRequest(serializers.Serializer):
    project_id = serializers.CharField(
        max_length=500,
        help_text="Repository URL (any form: https, SSH, with or without .git)",
    )
    client = serializers.CharField(
        max_length=100,
        required=False,
        help_text="The agent or integration, e.g. Claude Code. The key's name is built from it.",
    )
    # Older callers send `name`; it means the same as `client`.
    name = serializers.CharField(max_length=100, required=False, write_only=True)

    def validate(self, attrs):
        client = (attrs.pop("client", None) or attrs.pop("name", None) or "").strip()
        attrs.pop("name", None)
        if not client:
            raise serializers.ValidationError({"client": ["Choose a client or enter a name."]})
        attrs["client"] = client
        return attrs


class ClientSerializer(serializers.ModelSerializer):
    """A client as its owner sees it. Never includes the key or its hash."""

    has_key = serializers.SerializerMethodField()

    class Meta:
        model = Client
        fields = ["id", "name", "project_id", "created_at", "updated_at", "has_key"]

    def get_has_key(self, client) -> bool:
        key = getattr(client, "api_key", None)
        return bool(key and key.key_hash)


class IssuedKeySerializer(ClientSerializer):
    """Response to create and rotate: the only time the plaintext key is ever returned."""

    api_key = serializers.SerializerMethodField()

    class Meta(ClientSerializer.Meta):
        fields = [*ClientSerializer.Meta.fields, "api_key"]

    def get_api_key(self, client) -> str:
        return self.context["api_key"]
