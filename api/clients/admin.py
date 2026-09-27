"""Django admin configuration for clients app."""
from django.contrib import admin
from django.template.response import TemplateResponse

from .models import ApiKey, Client
from .services import issue_api_key

ISSUED_KEYS_TEMPLATE = "admin/clients/issued_keys.html"


def show_issued_keys(model_admin, request, issued, title):
    # Rendered directly, not via the messages framework, which would keep the plaintext key in
    # a cookie or the session until displayed.
    context = {
        **model_admin.admin_site.each_context(request),
        "title": title,
        "issued": issued,
        "opts": model_admin.model._meta,
    }
    return TemplateResponse(request, ISSUED_KEYS_TEMPLATE, context)


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ("name", "user_id", "project_id", "has_key", "created_at", "updated_at")
    list_filter = ("created_at", "updated_at", "user_id")
    search_fields = ("name", "project_id", "user_id")
    readonly_fields = ("id", "created_at", "updated_at")
    actions = ("regenerate_api_keys",)
    fieldsets = (
        (
            "Client Details",
            {"fields": ("id", "name", "user_id", "project_id")},
        ),
        (
            "Timestamps",
            {"fields": ("created_at", "updated_at")},
        ),
    )

    @admin.display(boolean=True, description="API key")
    def has_key(self, obj):
        key = getattr(obj, "api_key", None)
        return bool(key and key.key_hash)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if not change:
            obj._issued_api_key = issue_api_key(obj)

    def response_add(self, request, obj, post_url_continue=None):
        api_key = getattr(obj, "_issued_api_key", None)
        if api_key is None:
            return super().response_add(request, obj, post_url_continue)
        return show_issued_keys(self, request, [(obj, api_key)], "API key created")

    @admin.action(description="Regenerate API key (the old key stops working)")
    def regenerate_api_keys(self, request, queryset):
        issued = [(client, issue_api_key(client)) for client in queryset]
        return show_issued_keys(self, request, issued, "API keys regenerated")


@admin.register(ApiKey)
class ApiKeyAdmin(admin.ModelAdmin):
    """Read-only: keys are issued from the client admin, and only their hashes are stored."""

    list_display = ("id", "client", "created_at")
    list_filter = ("created_at", "client")
    search_fields = ("client__name", "key_hash")
    readonly_fields = ("id", "client", "key_hash", "created_at")
    fieldsets = (
        (
            "API Key",
            {"fields": ("id", "client", "key_hash")},
        ),
        (
            "Timestamps",
            {"fields": ("created_at",)},
        ),
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
