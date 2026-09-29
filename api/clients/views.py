"""
User API for API keys (ADR 028). Authenticated with a JWT from /api/v1/auth/token/; each user
manages only their own clients. Plaintext keys appear only in create and rotate responses.
"""
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import Http404
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from clients import services
from clients.models import Client
from clients.serializers import ClientSerializer, CreateClientRequest, IssuedKeySerializer


class ThrottledTokenObtainPairView(TokenObtainPairView):
    """Username and password in, JWT pair out. Throttled against password guessing."""

    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"


class ThrottledTokenRefreshView(TokenRefreshView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"


class UserApiView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    renderer_classes = [JSONRenderer]

    def own_client(self, request, client_id):
        try:
            return services.get_client(request.user, client_id)
        except Client.DoesNotExist as exc:
            raise Http404 from exc


def issued(client, api_key, status_code=status.HTTP_200_OK):
    body = IssuedKeySerializer(client, context={"api_key": api_key}).data
    return Response(body, status=status_code, headers={"Cache-Control": "no-store"})


class ClientListView(UserApiView):
    def get(self, request):
        clients = services.list_clients(request.user)
        return Response(ClientSerializer(clients, many=True).data)

    def post(self, request):
        data = CreateClientRequest(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            client, api_key = services.create_client_for_user(request.user, **data.validated_data)
        except DjangoValidationError as exc:
            raise ValidationError(exc.message_dict if hasattr(exc, "error_dict") else exc.messages)
        return issued(client, api_key, status.HTTP_201_CREATED)


class ClientDetailView(UserApiView):
    def get(self, request, client_id):
        return Response(ClientSerializer(self.own_client(request, client_id)).data)

    def delete(self, request, client_id):
        self.own_client(request, client_id)
        services.revoke_client(request.user, client_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


class RotateKeyView(UserApiView):
    def post(self, request, client_id):
        self.own_client(request, client_id)
        client, api_key = services.rotate_client_key(request.user, client_id)
        return issued(client, api_key)
