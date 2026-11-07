import secrets
import uuid

from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission

from quiz.models import QuizSession


def _safe_uuid(value):
    try:
        return uuid.UUID(str(value))
    except ValueError:
        return None


class HasSessionToken(BasePermission):
    """X-Session-Token başlığını oturumun token'ı ile karşılaştırır."""

    def has_permission(self, request, view):
        token = request.headers.get("X-Session-Token", "")
        session_uuid = _safe_uuid(view.kwargs.get("session_id"))
        session = (
            QuizSession.objects.select_related("category").filter(pk=session_uuid).first()
            if session_uuid
            else None
        )
        if not session or not token or not secrets.compare_digest(session.token, token):
            raise PermissionDenied("Geçersiz oturum anahtarı.")
        request.quiz_session = session
        return True
