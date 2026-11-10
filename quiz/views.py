from django.conf import settings
from django.db import connection
from django.db.models import Count, Q
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from quiz.models import Category
from quiz.permissions import HasSessionToken
from quiz.serializers import (
    AnswerSerializer,
    CategorySerializer,
    DuelCreateSerializer,
    DuelJoinSerializer,
    NameSerializer,
    StartSessionSerializer,
)
from quiz.services import duel as duel_svc
from quiz.services import i18n
from quiz.services import session as svc
from quiz.throttles import (
    AnswerThrottle,
    DuelAnswerThrottle,
    DuelCreateThrottle,
    DuelStatusThrottle,
    NameThrottle,
    SessionCreateThrottle,
)


class QuizErrorMixin:
    def handle_exception(self, exc):
        if isinstance(exc, svc.QuizError):
            return Response({"detail": exc.detail, **exc.extra}, status=exc.status_code)
        return super().handle_exception(exc)


class HealthView(APIView):
    authentication_classes = []
    permission_classes = []

    @extend_schema(exclude=True)
    def get(self, request):
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        return Response({"status": "ok"})


class LanguageListView(APIView):
    @extend_schema(responses=dict)
    def get(self, request):
        detected = i18n.resolve_language(
            request.query_params.get("lang"), request.headers.get("Accept-Language")
        )
        return Response(
            {
                "default": settings.QUIZ_DEFAULT_LANGUAGE,
                "detected": detected,
                "languages": [
                    {"code": code, "name": name} for code, name in settings.QUIZ_LANGUAGES.items()
                ],
            }
        )


class CategoryListView(APIView):
    @extend_schema(responses=CategorySerializer(many=True))
    def get(self, request):
        categories = Category.objects.filter(is_active=True).annotate(
            question_count=Count("questions", filter=Q(questions__is_approved=True))
        )
        language = i18n.resolve_language(
            request.query_params.get("lang"), request.headers.get("Accept-Language")
        )
        translated = i18n.category_texts(categories, language)
        data = CategorySerializer(categories, many=True).data
        for row in data:
            row["level_count"] = settings.QUIZ_LEVELS
            if row["id"] in translated:
                row["name"], row["description"] = translated[row["id"]]
        return Response(data)


def _player_id(request, body_value=None):
    """X-Player-Id başlığı (veya gövdedeki player_id); geçersizse None."""
    import uuid

    if body_value:
        return body_value
    raw = request.headers.get("X-Player-Id", "")
    try:
        return uuid.UUID(raw) if raw else None
    except ValueError:
        return None


class CategoryLevelsView(APIView):
    @extend_schema(responses=dict)
    def get(self, request, slug):
        category = Category.objects.filter(slug=slug, is_active=True).first()
        if not category:
            raise NotFound("Kategori bulunamadı.")
        return Response(svc.get_levels(category, _player_id(request)))


class SessionCreateView(QuizErrorMixin, APIView):
    throttle_classes = [SessionCreateThrottle]

    @extend_schema(request=StartSessionSerializer, responses=dict)
    def post(self, request):
        data = StartSessionSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        language = i18n.resolve_language(
            data.validated_data.get("language"), request.headers.get("Accept-Language")
        )
        session = svc.start_session(
            data.validated_data["category"],
            data.validated_data["platform"],
            language,
            level=data.validated_data["level"],
            player_id=_player_id(request, data.validated_data.get("player_id")),
        )
        return Response(
            {
                "session_id": str(session.id),
                "token": session.token,
                "category": session.category.slug,
                "language": session.language,
                "level": session.level,
                "total_questions": len(session.question_order),
                "time_limit_seconds": settings.QUIZ_TIME_LIMIT_SECONDS,
            },
            status=status.HTTP_201_CREATED,
        )


class SessionCurrentView(QuizErrorMixin, APIView):
    permission_classes = [HasSessionToken]

    @extend_schema(responses=dict)
    def get(self, request, session_id):
        return Response(svc.get_current(request.quiz_session))


class SessionAnswerView(QuizErrorMixin, APIView):
    permission_classes = [HasSessionToken]
    throttle_classes = [AnswerThrottle]

    @extend_schema(request=AnswerSerializer, responses=dict)
    def post(self, request, session_id):
        data = AnswerSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        result = svc.submit_answer(
            request.quiz_session,
            data.validated_data["question_id"],
            data.validated_data["choice_id"],
        )
        return Response(result)


class SessionResultView(QuizErrorMixin, APIView):
    permission_classes = [HasSessionToken]

    @extend_schema(responses=dict)
    def get(self, request, session_id):
        return Response(svc.get_result(request.quiz_session))


class SessionNameView(QuizErrorMixin, APIView):
    permission_classes = [HasSessionToken]
    throttle_classes = [NameThrottle]

    @extend_schema(request=NameSerializer, responses=dict)
    def post(self, request, session_id):
        data = NameSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        return Response(svc.save_name(request.quiz_session, data.validated_data["player_name"]))


class LeaderboardView(APIView):
    @extend_schema(responses=dict)
    def get(self, request):
        slug = request.query_params.get("category")
        category = None
        if slug:
            category = Category.objects.filter(slug=slug, is_active=True).first()
            if not category:
                raise NotFound("Kategori bulunamadı.")
        try:
            limit = max(1, min(10, int(request.query_params.get("limit", 10))))
        except ValueError:
            limit = 10
        mode = request.query_params.get("mode", "total")
        if mode == "best":
            # Eski davranış: her oyun ayrı satır
            rows = svc.leaderboard_qs(category).order_by("-score", "finished_at")[:limit]
            entries = [
                {
                    "rank": i,
                    "player_name": s.player_name,
                    "score": s.score,
                    "total_score": s.score,
                    "best_score": s.score,
                    "games_played": 1,
                    "finished_at": s.finished_at,
                }
                for i, s in enumerate(rows, start=1)
            ]
        else:
            rows = svc.leaderboard_players(category)[:limit]
            entries = [
                {
                    "rank": i,
                    "player_name": r["display_name"],
                    "score": r["total_score"],  # geriye dönük uyumluluk: toplam puan
                    "total_score": r["total_score"],
                    "best_score": r["best_score"],
                    "games_played": r["games_played"],
                    "finished_at": r["last_finished"],
                }
                for i, r in enumerate(rows, start=1)
            ]
        return Response({"category": slug or None, "mode": mode, "entries": entries})


class DuelCreateView(QuizErrorMixin, APIView):
    throttle_classes = [DuelCreateThrottle]

    @extend_schema(request=DuelCreateSerializer, responses=dict)
    def post(self, request):
        data = DuelCreateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        language = i18n.resolve_language(v.get("language"), request.headers.get("Accept-Language"))
        duel, host = duel_svc.create_duel(
            v["category"], v["level"], language, v["player_id"], v["player_name"]
        )
        return Response(
            {
                "code": duel.code,
                "role": host.role,
                "token": host.token,
                "status": duel.status,
                "category": duel.category.slug,
                "level": duel.level,
                "total_questions": len(duel.question_order),
                "time_limit_seconds": settings.QUIZ_TIME_LIMIT_SECONDS,
                "expires_in_seconds": settings.DUEL_LOBBY_TTL_SECONDS,
            },
            status=status.HTTP_201_CREATED,
        )


class DuelJoinView(QuizErrorMixin, APIView):
    throttle_classes = [DuelCreateThrottle]

    @extend_schema(request=DuelJoinSerializer, responses=dict)
    def post(self, request, code):
        data = DuelJoinSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        language = i18n.resolve_language(v.get("language"), request.headers.get("Accept-Language"))
        duel, guest = duel_svc.join_duel(code, v["player_id"], v["player_name"], language)
        return Response(
            {"code": duel.code, "role": guest.role, "token": guest.token, "status": duel.status}
        )


class DuelStateView(QuizErrorMixin, APIView):
    throttle_classes = [DuelStatusThrottle]

    @extend_schema(responses=dict)
    def get(self, request, code):
        return Response(duel_svc.get_state(code, request.headers.get("X-Duel-Token", "")))


class DuelAnswerView(QuizErrorMixin, APIView):
    throttle_classes = [DuelAnswerThrottle]

    @extend_schema(request=AnswerSerializer, responses=dict)
    def post(self, request, code):
        data = AnswerSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        result = duel_svc.submit_answer(
            code,
            request.headers.get("X-Duel-Token", ""),
            data.validated_data["question_id"],
            data.validated_data["choice_id"],
        )
        return Response(result)
