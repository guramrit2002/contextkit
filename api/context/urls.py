from django.urls import path

from context import views

app_name = "context"

urlpatterns = [
    path("briefing/", views.GetBriefingView.as_view(), name="briefing"),
    path("decisions/", views.LogDecisionView.as_view(), name="decisions"),
    path("state/", views.UpdateStateView.as_view(), name="state"),
    path("sessions/", views.LogSessionView.as_view(), name="sessions"),
    path("export/", views.ExportMarkdownView.as_view(), name="export"),
]
