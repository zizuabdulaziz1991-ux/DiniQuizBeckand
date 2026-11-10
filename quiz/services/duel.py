"""İki kişilik düello: aynı sorular, kilit adımlı (lock-step) turlar.

Sunucuda arka plan görevi yoktur. Faz geçişleri 'tembel' hesaplanır: her yoklama (GET) veya
cevap isteğinde `advance()` zaman damgalarına bakarak durumu ilerletir. Böylece durum
tamamen veritabanındadır ve birden çok worker'da tutarlı çalışır.

Tur akışı:  countdown → [question → reveal] x N → finished
  - question: iki oyuncu da cevaplayınca VEYA süre (limit + tolerans) dolunca biter
  - reveal:   REVEAL_SECONDS sürer; doğru şık ve rakibin seçimi görünür
"""

import random
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from quiz.models import Category, Choice, Duel, DuelAnswer, DuelPlayer, Question
from quiz.services.i18n import translated_question
from quiz.services.scoring import calculate_points
from quiz.services.session import QuizError
from quiz.validators import validate_player_name


def _err(detail, status, code, **extra):
    return QuizError(detail, status, {"code": code, **extra})


def _limit_ms() -> int:
    return settings.QUIZ_TIME_LIMIT_SECONDS * 1000


def _deadline_ms() -> int:
    return _limit_ms() + settings.QUIZ_GRACE_MS


def _clean_name(name: str) -> str:
    try:
        return validate_player_name(name)
    except DjangoValidationError as exc:
        raise _err(exc.messages[0], 400, "invalid_name")


# --------------------------------------------------------------------------- oluşturma / katılma


def create_duel(category_slug, level, language, player_id, player_name):
    try:
        category = Category.objects.get(slug=category_slug, is_active=True)
    except Category.DoesNotExist:
        raise _err("Kategori bulunamadı.", 404, "category_not_found")
    if not 1 <= level <= settings.QUIZ_LEVELS:
        raise _err(
            f"Seviye 1 ile {settings.QUIZ_LEVELS} arasında olmalı.", 400, "invalid_level"
        )
    name = _clean_name(player_name)

    ids = list(
        Question.objects.filter(category=category, is_approved=True, level=level).values_list(
            "id", flat=True
        )
    )
    if not ids:
        raise _err("Bu seviyede henüz soru yok.", 409, "level_empty", level=level)
    order = random.sample(ids, min(settings.QUIZ_QUESTION_COUNT, len(ids)))

    for _ in range(10):  # kod çakışmasına karşı yeniden dene
        try:
            with transaction.atomic():
                duel = Duel.objects.create(category=category, level=level, question_order=order)
                host = DuelPlayer.objects.create(
                    duel=duel,
                    role=DuelPlayer.Role.HOST,
                    player_id=player_id,
                    name=name,
                    language=language,
                )
            return duel, host
        except IntegrityError:
            continue
    raise _err("Düello oluşturulamadı, tekrar deneyin.", 503, "code_collision")


def _expire_if_stale(duel: Duel, now) -> None:
    if duel.status == Duel.Status.WAITING and now > duel.created_at + timedelta(
        seconds=settings.DUEL_LOBBY_TTL_SECONDS
    ):
        duel.status = Duel.Status.EXPIRED
        duel.save(update_fields=["status"])


def join_duel(code, player_id, player_name, language):
    now = timezone.now()
    with transaction.atomic():
        duel = Duel.objects.select_for_update().filter(code=code.strip().upper()).first()
        if duel is None:
            raise _err("Düello bulunamadı.", 404, "duel_not_found")
        _expire_if_stale(duel, now)
        if duel.status == Duel.Status.EXPIRED:
            raise _err("Düellonun süresi doldu.", 410, "duel_expired")
        if duel.status == Duel.Status.FINISHED:
            raise _err("Bu düello bitti.", 409, "duel_finished")
        if duel.status == Duel.Status.ACTIVE:
            raise _err("Bu düello dolu.", 409, "duel_full")

        host = duel.players.get(role=DuelPlayer.Role.HOST)
        if host.player_id == player_id:
            raise _err("Kendi düellona katılamazsın.", 400, "same_player")
        name = _clean_name(player_name)

        guest = DuelPlayer.objects.create(
            duel=duel,
            role=DuelPlayer.Role.GUEST,
            player_id=player_id,
            name=name,
            language=language,
        )
        duel.status = Duel.Status.ACTIVE
        duel.starts_at = now + timedelta(seconds=settings.DUEL_COUNTDOWN_SECONDS)
        duel.save(update_fields=["status", "starts_at"])
    return duel, guest


# --------------------------------------------------------------------------- tembel faz ilerletme


def advance(duel: Duel, now) -> None:
    """Zamana ve cevaplara bakarak düelloyu ilerletir (en fazla birkaç adım)."""
    if duel.status == Duel.Status.WAITING:
        _expire_if_stale(duel, now)
        return
    if duel.status != Duel.Status.ACTIVE:
        return

    total = len(duel.question_order)
    changed = False
    for _ in range(4 * total + 4):
        if duel.round_started_at is None:  # geri sayım
            if now >= duel.starts_at:
                duel.round_started_at = duel.starts_at
                duel.index = 0
                changed = True
                continue
            break

        if duel.reveal_until is None:  # soru aşaması
            deadline = duel.round_started_at + timedelta(milliseconds=_deadline_ms())
            answered = list(
                DuelAnswer.objects.filter(duel=duel, index=duel.index).values_list(
                    "answered_at", flat=True
                )
            )
            if len(answered) >= 2:
                end = min(max(answered), deadline)
            elif now >= deadline:
                end = deadline
            else:
                break
            duel.reveal_until = end + timedelta(seconds=settings.DUEL_REVEAL_SECONDS)
            changed = True
            continue

        if now >= duel.reveal_until:  # reveal bitti
            if duel.index >= total - 1:
                duel.status = Duel.Status.FINISHED
                duel.finished_at = duel.reveal_until
                changed = True
                break
            duel.index += 1
            duel.round_started_at = duel.reveal_until
            duel.reveal_until = None
            changed = True
            continue
        break

    if changed:
        duel.save()


def phase_of(duel: Duel) -> str:
    if duel.status == Duel.Status.WAITING:
        return "waiting"
    if duel.status in (Duel.Status.FINISHED, Duel.Status.EXPIRED):
        return "finished"
    if duel.round_started_at is None:
        return "countdown"
    if duel.reveal_until is None:
        return "question"
    return "reveal"


# --------------------------------------------------------------------------- yardımcılar


def _load(code, token, *, lock=True):
    qs = Duel.objects.select_for_update() if lock else Duel.objects
    duel = qs.filter(code=(code or "").strip().upper()).first()
    if duel is None:
        raise _err("Düello bulunamadı.", 404, "duel_not_found")
    players = list(duel.players.all())
    me = next((p for p in players if token and p.token == token), None)
    if me is None:
        raise _err("Geçersiz düello anahtarı.", 403, "invalid_token")
    opp = next((p for p in players if p.pk != me.pk), None)
    return duel, me, opp


def _touch(player: DuelPlayer, now) -> None:
    if player.last_seen is None or (now - player.last_seen).total_seconds() >= 2:
        player.last_seen = now
        player.save(update_fields=["last_seen"])


def _shuffled_choices(duel: Duel, question: Question):
    """Şık sırası düello+soru için sabit; iki oyuncu da aynı sırayı görür."""
    choices = list(question.choices.all().order_by("id"))
    random.Random(f"duel:{duel.pk}:{question.pk}").shuffle(choices)
    return choices


def _tally(answers, player_pk, upto):
    mine = [a for a in answers if a.player_id == player_pk and a.index <= upto]
    return sum(1 for a in mine if a.is_correct), sum(a.points for a in mine)


def _payload(duel: Duel, me: DuelPlayer, opp: DuelPlayer | None, now) -> dict:
    total = len(duel.question_order)
    phase = phase_of(duel)
    answers = list(duel.answers.all())
    by_key = {(a.player_id, a.index): a for a in answers}
    finished = duel.status == Duel.Status.FINISHED

    # Rakip sayıları yalnız açıklanmış (reveal edilmiş) turlar için görünür.
    if finished:
        revealed_upto = total - 1
    elif duel.reveal_until is not None:
        revealed_upto = duel.index
    else:
        revealed_upto = duel.index - 1
    if duel.round_started_at is None and not finished:
        revealed_upto = -1

    my_correct, my_points = _tally(answers, me.pk, total)
    opp_correct, opp_points = (_tally(answers, opp.pk, revealed_upto) if opp else (0, 0))

    in_round = phase in ("question", "reveal")
    my_answer = by_key.get((me.pk, duel.index)) if in_round else None
    opp_answer = by_key.get((opp.pk, duel.index)) if (in_round and opp) else None

    question = None
    reveal = None
    remaining_ms = None
    if in_round:
        q = Question.objects.get(pk=duel.question_order[duel.index])
        tq = translated_question(q, me.language)
        question = {
            "id": q.id,
            "text": tq["text"],
            "arabic_text": q.arabic_text or None,
            "choices": [
                {"id": c.id, "text": tq["choices"][c.id]} for c in _shuffled_choices(duel, q)
            ],
        }
        if phase == "question":
            ends = duel.round_started_at + timedelta(milliseconds=_limit_ms())
            remaining_ms = max(0, int((ends - now).total_seconds() * 1000))
        else:
            correct = q.choices.filter(is_correct=True).first()
            reveal = {
                "index": duel.index,
                "correct_choice_id": correct.id if correct else None,
                "explanation": tq["explanation"],
                "my_choice_id": my_answer.choice_id if my_answer else None,
                "opponent_choice_id": opp_answer.choice_id if opp_answer else None,
                "my_correct": bool(my_answer and my_answer.is_correct),
                "opponent_correct": bool(opp_answer and opp_answer.is_correct),
                "my_points": my_answer.points if my_answer else 0,
                "opponent_points": opp_answer.points if opp_answer else 0,
            }

    starts_in_ms = None
    if phase == "countdown":
        starts_in_ms = max(0, int((duel.starts_at - now).total_seconds() * 1000))

    connected = bool(
        opp
        and opp.last_seen
        and (now - opp.last_seen).total_seconds() <= settings.DUEL_CONNECTED_SECONDS
    )

    result = None
    if finished:
        t_me, t_opp = (my_correct, my_points), (opp_correct, opp_points)
        if t_me > t_opp:
            winner = "me"
        elif t_me < t_opp:
            winner = "opponent"
        else:
            winner = "draw"
        result = {
            "winner": winner,
            "me": {"correct": my_correct, "points": my_points},
            "opponent": {"correct": opp_correct, "points": opp_points},
        }

    return {
        "code": duel.code,
        "status": duel.status,
        "phase": phase,
        "category": duel.category.slug,
        "level": duel.level,
        "total_questions": total,
        "time_limit_seconds": settings.QUIZ_TIME_LIMIT_SECONDS,
        "starts_in_ms": starts_in_ms,
        "index": duel.index if in_round else 0,
        "question": question,
        "remaining_ms": remaining_ms,
        "me": {
            "role": me.role,
            "name": me.name,
            "answered": my_answer is not None,
            "correct": my_correct,
            "points": my_points,
        },
        "opponent": {
            "name": opp.name if opp else None,
            "answered": opp_answer is not None,
            "correct": opp_correct,
            "points": opp_points,
            "connected": connected,
        },
        "reveal": reveal,
        "result": result,
    }


# --------------------------------------------------------------------------- durum / cevap


def get_state(code, token) -> dict:
    now = timezone.now()
    with transaction.atomic():
        duel, me, opp = _load(code, token)
        advance(duel, now)
        _touch(me, now)
        return _payload(duel, me, opp, now)


def submit_answer(code, token, question_id, choice_id) -> dict:
    now = timezone.now()
    with transaction.atomic():
        duel, me, opp = _load(code, token)
        advance(duel, now)
        _touch(me, now)

        if duel.status != Duel.Status.ACTIVE or duel.round_started_at is None:
            raise _err("Düello şu an cevap kabul etmiyor.", 409, "not_active")
        if duel.reveal_until is not None:
            raise _err("Bu tur bitti.", 409, "round_over")

        expected = duel.question_order[duel.index]
        if DuelAnswer.objects.filter(duel=duel, player=me, index=duel.index).exists():
            raise _err("Bu soruyu zaten cevapladın.", 409, "already_answered")
        if question_id != expected:
            raise _err("Bu soru şu an cevaplanamaz.", 400, "wrong_question")

        question = Question.objects.get(pk=expected)
        choice = None
        if choice_id is not None:
            try:
                choice = question.choices.get(pk=choice_id)
            except Choice.DoesNotExist:
                raise _err("Geçersiz şık.", 400, "invalid_choice")

        elapsed_ms = max(0, int((now - duel.round_started_at).total_seconds() * 1000))
        is_correct = bool(choice and choice.is_correct)
        points = calculate_points(elapsed_ms, is_correct)
        try:
            with transaction.atomic():
                DuelAnswer.objects.create(
                    duel=duel,
                    player=me,
                    index=duel.index,
                    question=question,
                    choice=choice,
                    is_correct=is_correct,
                    elapsed_ms=elapsed_ms,
                    points=points,
                    answered_at=now,
                )
        except IntegrityError:
            raise _err("Bu soruyu zaten cevapladın.", 409, "already_answered")

        advance(duel, now)  # iki oyuncu da cevapladıysa tur hemen reveal'e geçer
        correct = question.choices.filter(is_correct=True).first()
        return {
            "is_correct": is_correct,
            "correct_choice_id": correct.id if correct else None,
            "points": points,
            "explanation": translated_question(question, me.language)["explanation"],
        }
