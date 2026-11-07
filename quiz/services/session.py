import random
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from quiz.models import Category, Choice, Question, QuizSession, SessionAnswer
from quiz.services.scoring import calculate_points, max_score


class QuizError(Exception):
    """API'ye HTTP durum koduyla çevrilen iş kuralı hatası."""

    def __init__(self, detail, status_code=400, extra=None):
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code
        self.extra = extra or {}


def start_session(category_slug: str, platform: str) -> QuizSession:
    try:
        category = Category.objects.get(slug=category_slug, is_active=True)
    except Category.DoesNotExist:
        raise QuizError("Kategori bulunamadı.", 404)

    ids = list(
        Question.objects.filter(category=category, is_approved=True).values_list("id", flat=True)
    )
    if not ids:
        raise QuizError("Bu kategoride henüz onaylı soru yok.", 409)
    count = min(settings.QUIZ_QUESTION_COUNT, len(ids))
    order = random.sample(ids, count)
    return QuizSession.objects.create(
        category=category, question_order=order, client_platform=platform
    )


def ensure_not_expired(session: QuizSession) -> None:
    """Süresi geçen aktif oturumu 'expired' yapar ve 410 döndürür."""
    if session.status == QuizSession.Status.EXPIRED:
        raise QuizError("Oturumun süresi doldu.", 410)
    ttl = timedelta(minutes=settings.QUIZ_SESSION_TTL_MINUTES)
    if session.status == QuizSession.Status.ACTIVE and session.started_at < timezone.now() - ttl:
        session.status = QuizSession.Status.EXPIRED
        session.save(update_fields=["status"])
        raise QuizError("Oturumun süresi doldu.", 410)


def _time_limit_ms() -> int:
    return settings.QUIZ_TIME_LIMIT_SECONDS * 1000


def _shuffled_choices(session: QuizSession, question: Question):
    """Şık sırası oturum+soru için sabit karıştırılır (sayfa yenilemede değişmez)."""
    choices = list(question.choices.all().order_by("id"))
    random.Random(f"{session.id}:{question.id}").shuffle(choices)
    return choices


def get_current(session: QuizSession) -> dict:
    with transaction.atomic():
        session = QuizSession.objects.select_for_update().get(pk=session.pk)
        ensure_not_expired(session)
        if session.status == QuizSession.Status.FINISHED:
            raise QuizError("Quiz tamamlandı.", 409, {"status": "finished"})

        now = timezone.now()
        if session.current_served_at is None:
            session.current_served_at = now
            session.save(update_fields=["current_served_at"])

        elapsed_ms = int((now - session.current_served_at).total_seconds() * 1000)
        remaining_ms = max(0, _time_limit_ms() - elapsed_ms)
        question = Question.objects.get(pk=session.question_order[session.current_index])
        return {
            "index": session.current_index,
            "total": len(session.question_order),
            "question": {
                "id": question.id,
                "text": question.text,
                "arabic_text": question.arabic_text or None,
                "choices": [
                    {"id": c.id, "text": c.text} for c in _shuffled_choices(session, question)
                ],
            },
            "remaining_ms": remaining_ms,
            "score": session.score,
        }


def submit_answer(session: QuizSession, question_id: int, choice_id: int | None) -> dict:
    with transaction.atomic():
        session = QuizSession.objects.select_for_update().get(pk=session.pk)
        ensure_not_expired(session)
        if session.status == QuizSession.Status.FINISHED:
            raise QuizError("Quiz tamamlandı.", 409, {"status": "finished"})

        if SessionAnswer.objects.filter(session=session, question_id=question_id).exists():
            raise QuizError("Bu soru zaten cevaplandı.", 409)

        expected = session.question_order[session.current_index]
        if question_id != expected:
            raise QuizError("Bu soru şu an cevaplanamaz.", 400)
        if session.current_served_at is None:
            raise QuizError("Soru henüz istenmedi.", 400)

        question = Question.objects.get(pk=expected)
        now = timezone.now()
        elapsed_ms = int((now - session.current_served_at).total_seconds() * 1000)
        timed_out = elapsed_ms > _time_limit_ms() + settings.QUIZ_GRACE_MS

        choice = None
        if choice_id is not None and not timed_out:
            try:
                choice = question.choices.get(pk=choice_id)
            except Choice.DoesNotExist:
                raise QuizError("Geçersiz şık.", 400)

        is_correct = bool(choice and choice.is_correct)
        points = calculate_points(elapsed_ms, is_correct)
        correct_choice = question.choices.filter(is_correct=True).first()

        try:
            with transaction.atomic():
                SessionAnswer.objects.create(
                    session=session,
                    question=question,
                    choice=choice,
                    is_correct=is_correct,
                    elapsed_ms=elapsed_ms,
                    points=points,
                )
        except IntegrityError:
            raise QuizError("Bu soru zaten cevaplandı.", 409)

        session.score += points
        if choice is None:
            session.empty_count += 1
        elif is_correct:
            session.correct_count += 1
        else:
            session.wrong_count += 1
        session.current_index += 1
        session.current_served_at = None
        is_last = session.current_index >= len(session.question_order)
        if is_last:
            session.status = QuizSession.Status.FINISHED
            session.finished_at = now
        session.save()

        return {
            "is_correct": is_correct,
            "correct_choice_id": correct_choice.id if correct_choice else None,
            "points": points,
            "total_score": session.score,
            "explanation": question.explanation,
            "is_last": is_last,
        }


def leaderboard_qs(category: Category | None = None):
    qs = QuizSession.objects.filter(status=QuizSession.Status.FINISHED).exclude(player_name="")
    if category:
        qs = qs.filter(category=category)
    return qs


def rank_of(session: QuizSession) -> int:
    """Kategori skor tablosunda bu oturumun sırası (eşitlikte erken bitiren önde)."""
    ahead = (
        leaderboard_qs(session.category)
        .exclude(pk=session.pk)
        .filter(
            Q(score__gt=session.score)
            | Q(score=session.score, finished_at__lt=session.finished_at)
        )
        .count()
    )
    return ahead + 1


def get_result(session: QuizSession) -> dict:
    ensure_not_expired(session)
    if session.status != QuizSession.Status.FINISHED:
        raise QuizError("Quiz henüz bitmedi.", 409)
    return {
        "score": session.score,
        "correct_count": session.correct_count,
        "wrong_count": session.wrong_count,
        "empty_count": session.empty_count,
        "max_score": max_score(len(session.question_order)),
        "rank_preview": rank_of(session),
    }


def save_name(session: QuizSession, name: str) -> dict:
    with transaction.atomic():
        session = QuizSession.objects.select_for_update().get(pk=session.pk)
        ensure_not_expired(session)
        if session.status != QuizSession.Status.FINISHED:
            raise QuizError("İsim yalnızca biten quize yazılabilir.", 409)
        if session.player_name:
            raise QuizError("İsim zaten kaydedildi.", 409)
        session.player_name = name
        session.save(update_fields=["player_name"])
    rank = rank_of(session)
    return {"rank": rank, "in_top_10": rank <= 10}
