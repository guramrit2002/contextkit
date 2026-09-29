"""POST /api/v1/auth/github/: GitHub OAuth code in, contextkit JWT pair out (ADR 028)."""
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from accounts import github, services


class GitHubSignInRequest(serializers.Serializer):
    code = serializers.CharField(max_length=200)
    redirect_uri = serializers.URLField(max_length=500, required=False)


class GitHubSignInView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    renderer_classes = [JSONRenderer]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        if not github.is_configured():
            return Response(
                {"detail": "GitHub sign-in is not configured on this server."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        data = GitHubSignInRequest(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            tokens = services.sign_in_with_github(**data.validated_data)
        except github.GitHubAuthError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except services.SignInNotAllowed as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        return Response(tokens, headers={"Cache-Control": "no-store"})
