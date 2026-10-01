from django.contrib import admin

from .models import GitHubIdentity


@admin.register(GitHubIdentity)
class GitHubIdentityAdmin(admin.ModelAdmin):
    list_display = ("login", "github_id", "user", "created_at")
    search_fields = ("login", "user__username")
    readonly_fields = ("github_id", "login", "user", "created_at", "updated_at")
