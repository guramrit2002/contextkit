from django.urls import path

from clients import views

app_name = "clients"

urlpatterns = [
    path("auth/token/", views.ThrottledTokenObtainPairView.as_view(), name="token"),
    path("auth/token/refresh/", views.ThrottledTokenRefreshView.as_view(), name="token-refresh"),
    path("clients/", views.ClientListView.as_view(), name="client-list"),
    path("clients/<str:client_id>/", views.ClientDetailView.as_view(), name="client-detail"),
    path("clients/<str:client_id>/rotate/", views.RotateKeyView.as_view(), name="client-rotate"),
]
