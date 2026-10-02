from django.urls import path

from accounts import views

app_name = "accounts"

urlpatterns = [
    path("auth/github/", views.GitHubSignInView.as_view(), name="github"),
    path("github/repos/", views.GitHubReposView.as_view(), name="github-repos"),
]
