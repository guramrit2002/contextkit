"""DRF authentication for agents using their API key. Verification lives in core.auth."""
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from core.auth import AgentContext, authenticate_request
from core.errors import AuthenticationError


class AuthenticatedAgent:
    """request.user for agent requests. Not a Django user; carries the agent's identity."""

    is_authenticated = True
    is_anonymous = False

    def __init__(self, context: AgentContext):
        self.context = context
        self.pk = context.agent_id

    def __str__(self) -> str:
        return f"agent {self.context.agent_id}"


def bearer_token(request) -> str | None:
    header = request.META.get("HTTP_AUTHORIZATION", "").strip()
    if not header:
        return None
    scheme, _, token = header.partition(" ")
    if scheme.lower() == "bearer" and token.strip():
        return token.strip()
    # A malformed header is still an attempt to authenticate: pass it on so it is denied.
    return header


def requested_project_id(request) -> str | None:
    if request.method == "GET":
        return request.query_params.get("project_id") or None
    data = request.data
    project_id = data.get("project_id") if hasattr(data, "get") else None
    return project_id if isinstance(project_id, str) and project_id else None


class AgentKeyAuthentication(BaseAuthentication):
    """
    Requires `Authorization: Bearer <key>` on every request; there is no keyless local mode
    over REST. Views set `audit_tool_name` so denials are audited under the right tool.
    """

    def authenticate(self, request):
        view = request.parser_context.get("view")
        tool_name = getattr(view, "audit_tool_name", "rest_api")
        api_key = bearer_token(request)
        try:
            agent = authenticate_request(
                tool_name, api_key, requested_project_id(request), key_required=True
            )
        except AuthenticationError as exc:
            raise AuthenticationFailed(str(exc)) from exc

        request.agent_context = agent
        return AuthenticatedAgent(agent), api_key

    def authenticate_header(self, request) -> str:
        # Makes DRF answer 401 (not 403) with a WWW-Authenticate challenge.
        return 'Bearer realm="contextkit"'
