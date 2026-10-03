"""
POST /api/v1/auth/github/: GitHub OAuth code in, contextkit JWT pair out (ADR 028).
GET /api/v1/auth/github/mock-authorize/: local development only, stands in for GitHub's page.
GET /api/v1/github/repos/: the signed-in user's public repositories (ADR 030).
"""
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from accounts import github, mock_github, services


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


class GitHubReposView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    renderer_classes = [JSONRenderer]

    def get(self, request):
        if not github.is_configured():
            return Response(
                {"detail": "GitHub sign-in is not configured on this server."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        try:
            return Response(services.github_repositories(request.user))
        except github.GitHubAuthError as exc:
            # The website falls back to typing the URL.
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)


LOCAL_HOSTS = ("localhost", "127.0.0.1")


def mock_authorize(request):
    """
    Stand-in for github.com/login/oauth/authorize when GITHUB_MOCK is on (local only): sends the
    browser straight back to the website with a code, as if the user had approved.
    """
    from urllib.parse import urlencode, urlsplit

    from django.http import Http404, HttpResponseBadRequest, HttpResponseRedirect

    if not mock_github.enabled():
        raise Http404
    redirect_uri, state = request.GET.get("redirect_uri", ""), request.GET.get("state", "")
    target = urlsplit(redirect_uri)
    if target.scheme not in ("http", "https") or target.hostname not in LOCAL_HOSTS or not state:
        return HttpResponseBadRequest("redirect_uri must be a localhost URL; state is required.")
    query = urlencode({"code": "mock", "state": state})
    separator = "&" if target.query else "?"
    return HttpResponseRedirect(f"{redirect_uri}{separator}{query}")
