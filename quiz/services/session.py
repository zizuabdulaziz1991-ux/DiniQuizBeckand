import random
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Count, Max, Q, Sum, Value
from django.db.models.functions import Lower
from django.utils import timezone

from quiz.models import (
    Category,
    Choice,
    LevelProgress,
    Question,
    QuizSession,
    SessionAnswer,
)
from quiz.services.i18n import translated_question
from quiz.services.scoring import calculate_points, max_score


class QuizError(Exception):
    """API'ye HTTP durum koduyla çevrilen iş kuralı hatası."""

    def __init__(self, detail, status_code=400, extra=None):
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code
        self.extra = extra or {}


def _passed_levels(player_id, category) -> set[int]:
    if not player_id:
        return set()
    return set(
        LevelProgress.objects.filter(player_id=player_id, category=category, passed=True)
        .values_list("level", flat=True)
    )


def is_level_unlocked(level: int, passed: set[int]) -> bool:
    """1. seviye herkese açık; n. seviye için (n-1). seviye 10/10 tamamlanmış olmalı."""
    return level == 1 or (level - 1) in passed


def start_session(
    category_slug: str,
    platform: str,
    language: str = "tr",
    level: int = 1,
    player_id=None,
) -> QuizSession:
    try:
        category = Category.objects.get(slug=category_slug, is_active=True)
    except Category.DoesNotExist:
        raise QuizError("Kategori bulunamadı.", 404)

    if not 1 <= level <= settings.QUIZ_LEVELS:
        raise QuizError(
            f"Seviye 1 ile {settings.QUIZ_LEVELS} arasında olmalı.", 400, {"code": "invalid_level"}
        )
    if not is_level_unlocked(level, _passed_levels(player_id, category)):
        raise QuizError(
            "Bu seviye henüz açılmadı: önceki seviyeyi %100 doğru bitirmelisin.",
            403,
            {"code": "level_locked", "level": level},
        )

    ids = list(
        Question.objects.filter(category=category, is_approved=True, level=level).values_list(
            "id", flat=True
        )
    )
    if not ids:
        raise QuizError(
            "Bu seviyede henüz soru yok.", 409, {"code": "level_empty", "level": level}
        )
    count = min(settings.QUIZ_QUESTION_COUNT, len(ids))
    order = random.sample(ids, count)
    return QuizSession.objects.create(
        category=category,
        question_order=order,
        client_platform=platform,
        language=language,
        level=level,
        player_id=player_id,
    )


def _record_progress(session: QuizSession) -> tuple[bool, bool]:
    """Biten oyunu oyuncu ilerlemesine yazar → (mükemmel mi, sonraki seviye yeni mi açıldı)."""
    perfect = session.correct_count == len(session.question_order)
    newly = False
    if session.player_id:
        progress, _ = LevelProgress.objects.select_for_update().get_or_create(
            player_id=session.player_id, category=session.category, level=session.level
        )
        newly = perfect and not progress.passed and session.level < settings.QUIZ_LEVELS
        progress.attempts += 1
        progress.best_correct = max(progress.best_correct, session.correct_count)
        progress.passed = progress.passed or perfect
        progress.save()
    return perfect, newly


def _next_level(session: QuizSession, perfect: bool):
    if perfect and session.level < settings.QUIZ_LEVELS:
        return session.level + 1
    return None


def get_levels(category: Category, player_id=None) -> dict:
    """Kategorinin seviye listesi ve oyuncunun durumu."""
    counts = dict(
        Question.objects.filter(category=category, is_approved=True)
        .values_list("level")
        .annotate(n=Count("id"))
        .order_by()
    )
    rows = {}
    if player_id:
        rows = {
            p.level: p
            for p in LevelProgress.objects.filter(player_id=player_id, category=category)
        }
    passed = {lv for lv, p in rows.items() if p.passed}
    levels = []
    for lv in range(1, settings.QUIZ_LEVELS + 1):
        n = counts.get(lv, 0)
        if n == 0:
            status = "empty"
        elif lv in passed:
            status = "completed"
        elif is_level_unlocked(lv, passed):
            status = "unlocked"
        else:
            status = "locked"
        p = rows.get(lv)
        levels.append(
            {
                "level": lv,
                "status": status,
                "question_count": min(n, settings.QUIZ_QUESTION_COUNT),
                "best_correct": p.best_correct if p else 0,
                "attempts": p.attempts if p else 0,
            }
        )
    return {
        "category": category.slug,
        "level_count": settings.QUIZ_LEVELS,
        "questions_per_level": settings.QUIZ_QUESTION_COUNT,
        "levels": levels,
    }


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
        tq = translated_question(question, session.language)
        return {
            "language": session.language,
            "level": session.level,
            "index": session.current_index,
            "total": len(session.question_order),
            "question": {
                "id": question.id,
                "text": tq["text"],
                "arabic_text": question.arabic_text or None,
                "choices": [
                    {"id": c.id, "text": tq["choices"][c.id]}
                    for c in _shuffled_choices(session, question)
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
        perfect = False
        if is_last:
            session.status = QuizSession.Status.FINISHED
            session.finished_at = now
            perfect, session.newly_unlocked = _record_progress(session)
        session.save()

        result = {
            "is_correct": is_correct,
            "correct_choice_id": correct_choice.id if correct_choice else None,
            "points": points,
            "total_score": session.score,
            "explanation": translated_question(question, session.language)["explanation"],
            "is_last": is_last,
        }
        if is_last:
            result.update(
                {
                    "level": session.level,
                    "perfect": perfect,
                    "level_passed": perfect,
                    "next_level": _next_level(session, perfect),
                    "newly_unlocked": session.newly_unlocked,
                }
            )
        return result


def leaderboard_qs(category: Category | None = None):
    qs = QuizSession.objects.filter(status=QuizSession.Status.FINISHED).exclude(player_name="")
    if category:
        qs = qs.filter(category=category)
    return qs


def leaderboard_players(category: Category | None = None):
    """Oyuncu (isim, büyük/küçük harf duyarsız) bazında toplanmış skor satırları.

    Aynı isimle oynanan tüm biten oyunlar tek satırda birleşir:
    total_score (toplam), best_score (en iyi oyun), games_played (oyun sayısı).
    Sıralama: toplam puan azalan, eşitlikte son oyununu daha önce bitiren önde.
    """
    return (
        leaderboard_qs(category)
        .annotate(pname=Lower("player_name"))
        .values("pname")
        .annotate(
            display_name=Max("player_name"),
            total_score=Sum("score"),
            best_score=Max("score"),
            games_played=Count("id"),
            last_finished=Max("finished_at"),
        )
        .order_by("-total_score", "last_finished")
    )


def _players_ahead(category, total, last_finished) -> int:
    return (
        leaderboard_players(category)
        .filter(
            Q(total_score__gt=total) | Q(total_score=total, last_finished__lt=last_finished)
        )
        .count()
    )


def rank_of(session: QuizSession) -> int:
    """Kategori skor tablosunda oyuncunun (toplam puana göre) sırası."""
    me = (
        leaderboard_players(session.category)
        .filter(pname=Lower(Value(session.player_name)))
        .first()
    )
    if me is None:
        return rank_preview(session)
    return _players_ahead(session.category, me["total_score"], me["last_finished"]) + 1


def rank_preview(session: QuizSession) -> int:
    """Henüz isim yazılmamış oyunun puanıyla yeni bir oyuncu olarak alacağı sıra."""
    return _players_ahead(session.category, session.score, session.finished_at) + 1


def get_result(session: QuizSession) -> dict:
    ensure_not_expired(session)
    if session.status != QuizSession.Status.FINISHED:
        raise QuizError("Quiz henüz bitmedi.", 409)
    perfect = session.correct_count == len(session.question_order)
    return {
        "score": session.score,
        "correct_count": session.correct_count,
        "wrong_count": session.wrong_count,
        "empty_count": session.empty_count,
        "max_score": max_score(len(session.question_order)),
        "rank_preview": rank_preview(session),
        "total_questions": len(session.question_order),
        "level": session.level,
        "perfect": perfect,
        "level_passed": perfect,
        "next_level": _next_level(session, perfect),
        "newly_unlocked": session.newly_unlocked,
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
