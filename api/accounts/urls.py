from django.urls import path

from accounts import views

app_name = "accounts"

urlpatterns = [
    path("auth/github/", views.GitHubSignInView.as_view(), name="github"),
    path("auth/github/mock-authorize/", views.mock_authorize, name="github-mock-authorize"),
    path("github/repos/", views.GitHubReposView.as_view(), name="github-repos"),
]
