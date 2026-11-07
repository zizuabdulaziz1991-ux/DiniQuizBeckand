from django.urls import path

from quiz import views

urlpatterns = [
    path("health/", views.HealthView.as_view(), name="health"),
    path("categories/", views.CategoryListView.as_view(), name="categories"),
    path("sessions/", views.SessionCreateView.as_view(), name="session-create"),
    path(
        "sessions/<str:session_id>/current/",
        views.SessionCurrentView.as_view(),
        name="session-current",
    ),
    path(
        "sessions/<str:session_id>/answer/",
        views.SessionAnswerView.as_view(),
        name="session-answer",
    ),
    path(
        "sessions/<str:session_id>/result/",
        views.SessionResultView.as_view(),
        name="session-result",
    ),
    path(
        "sessions/<str:session_id>/name/",
        views.SessionNameView.as_view(),
        name="session-name",
    ),
    path("leaderboard/", views.LeaderboardView.as_view(), name="leaderboard"),
]
