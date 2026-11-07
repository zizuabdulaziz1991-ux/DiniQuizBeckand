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
    NameSerializer,
    StartSessionSerializer,
)
from quiz.services import session as svc
from quiz.throttles import AnswerThrottle, NameThrottle, SessionCreateThrottle


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


class CategoryListView(APIView):
    @extend_schema(responses=CategorySerializer(many=True))
    def get(self, request):
        categories = Category.objects.filter(is_active=True).annotate(
            question_count=Count("questions", filter=Q(questions__is_approved=True))
        )
        return Response(CategorySerializer(categories, many=True).data)


class SessionCreateView(QuizErrorMixin, APIView):
    throttle_classes = [SessionCreateThrottle]

    @extend_schema(request=StartSessionSerializer, responses=dict)
    def post(self, request):
        data = StartSessionSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        session = svc.start_session(
            data.validated_data["category"], data.validated_data["platform"]
        )
        return Response(
            {
                "session_id": str(session.id),
                "token": session.token,
                "category": session.category.slug,
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
        rows = svc.leaderboard_qs(category).order_by("-score", "finished_at")[:limit]
        entries = [
            {
                "rank": i,
                "player_name": s.player_name,
                "score": s.score,
                "finished_at": s.finished_at,
            }
            for i, s in enumerate(rows, start=1)
        ]
        return Response({"category": slug or None, "entries": entries})
