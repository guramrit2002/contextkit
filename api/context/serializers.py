"""Request shapes for the agent context REST API. Content rules live in core.validation."""
from rest_framework import serializers

PROJECT_ID = {"required": False, "allow_null": True, "max_length": 500}
OPTIONAL_TEXT = {"required": False, "allow_null": True, "allow_blank": True}


class BriefingQuery(serializers.Serializer):
    project_id = serializers.CharField(**PROJECT_ID)


class LogDecisionRequest(serializers.Serializer):
    project_id = serializers.CharField(**PROJECT_ID)
    decision = serializers.CharField()
    reasoning = serializers.CharField()
    alternatives_considered = serializers.CharField(**OPTIONAL_TEXT)


class UpdateStateRequest(serializers.Serializer):
    project_id = serializers.CharField(**PROJECT_ID)
    progress = serializers.CharField()
    next_steps = serializers.CharField()
    blockers = serializers.CharField(**OPTIONAL_TEXT)


class LogSessionRequest(serializers.Serializer):
    project_id = serializers.CharField(**PROJECT_ID)
    summary = serializers.CharField()
    decisions_made = serializers.CharField(**OPTIONAL_TEXT)


class ExportRequest(serializers.Serializer):
    project_id = serializers.CharField(**PROJECT_ID)
    format = serializers.ChoiceField(choices=["markdown"], default="markdown")
