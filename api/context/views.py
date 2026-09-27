"""
Agent context REST API: the MCP tools over HTTP for clients without MCP.

Each view validates the request shape and makes one core.services call through
core.auth.run_as_agent, which enforces the agent's project and writes the audit row.
"""
import logging

from asgiref.sync import async_to_sync
from rest_framework import status
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.serializers import Serializer
from rest_framework.views import APIView

from agents.authentication import AgentKeyAuthentication
from context import serializers
from core import services
from core.auth import run_as_agent
from core.errors import AuthorizationError
from core.errors import ValidationError as CoreValidationError

logger = logging.getLogger(__name__)


class ServiceFailed(APIException):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_detail = "The request could not be completed."
    default_code = "service_error"


class AgentContextView(APIView):
    authentication_classes = [AgentKeyAuthentication]
    permission_classes = [IsAuthenticated]
    renderer_classes = [JSONRenderer]
    audit_tool_name: str
    request_serializer: type[Serializer]

    def validated(self, data) -> dict:
        serializer = self.request_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data

    def run(self, request, project_id, operation):
        try:
            return async_to_sync(run_as_agent)(
                self.audit_tool_name, request.agent_context, project_id, operation
            )
        except AuthorizationError as exc:
            raise PermissionDenied(str(exc)) from exc
        except (CoreValidationError, ValueError, TypeError) as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        except Exception as exc:
            # Already audited with detail; never echo internals to the client.
            logger.exception("%s failed", self.audit_tool_name)
            raise ServiceFailed() from exc


class GetBriefingView(AgentContextView):
    audit_tool_name = "get_context"
    request_serializer = serializers.BriefingQuery

    def get(self, request):
        data = self.validated(request.query_params)
        project_id = data.get("project_id")
        briefing = self.run(request, project_id, lambda: services.get_briefing(project_id))
        return Response(briefing)


class LogDecisionView(AgentContextView):
    audit_tool_name = "log_decision"
    request_serializer = serializers.LogDecisionRequest

    def post(self, request):
        data = self.validated(request.data)
        record = self.run(
            request,
            data.get("project_id"),
            lambda: services.log_decision(
                project_id=data.get("project_id"),
                decision=data["decision"],
                reasoning=data["reasoning"],
                alternatives_considered=data.get("alternatives_considered") or None,
            ),
        )
        return Response(
            {"success": True, "decision_id": record["id"], "created_at": record["created_at"]},
            status=status.HTTP_201_CREATED,
        )


class UpdateStateView(AgentContextView):
    audit_tool_name = "update_state"
    request_serializer = serializers.UpdateStateRequest

    def post(self, request):
        data = self.validated(request.data)
        record = self.run(
            request,
            data.get("project_id"),
            lambda: services.update_state(
                project_id=data.get("project_id"),
                progress=data["progress"],
                next_steps=data["next_steps"],
                blockers=data.get("blockers") or None,
            ),
        )
        return Response({"success": True, "updated_at": record["updated_at"]})


class LogSessionView(AgentContextView):
    audit_tool_name = "log_session"
    request_serializer = serializers.LogSessionRequest

    def post(self, request):
        data = self.validated(request.data)
        record = self.run(
            request,
            data.get("project_id"),
            lambda: services.log_session(
                project_id=data.get("project_id"),
                summary=data["summary"],
                decisions_made=data.get("decisions_made") or None,
            ),
        )
        return Response(
            {"success": True, "session_id": record["id"], "created_at": record["created_at"]},
            status=status.HTTP_201_CREATED,
        )


class ExportMarkdownView(AgentContextView):
    audit_tool_name = "export_markdown"
    request_serializer = serializers.ExportRequest

    def post(self, request):
        data = self.validated(request.data)
        project_id = data.get("project_id")
        content = self.run(request, project_id, lambda: services.export_markdown(project_id))
        return Response({
            "success": True,
            "format": data["format"],
            "content": content,
            "size_bytes": len(content.encode("utf-8")),
        })
