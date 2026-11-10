import uuid
from datetime import timedelta

import pytest
from freezegun import freeze_time

from quiz.models import Choice, Duel, LevelProgress, Question, QuestionTranslation, QuizSession
from quiz.tests.test_levels import make_questions

BASE = "/api/v1/duels/"


@pytest.fixture
def pool(category):
    make_questions(category, 1, 10)
    return category


def create(client, player=None, name="Ahmet", level=1, language="tr", category="siyer"):
    return client.post(
        BASE,
        {
            "category": category,
            "level": level,
            "language": language,
            "player_id": str(player or uuid.uuid4()),
            "player_name": name,
        },
        format="json",
    )


def join(client, code, player=None, name="Ali", language="tr"):
    return client.post(
        f"{BASE}{code}/join/",
        {"player_id": str(player or uuid.uuid4()), "player_name": name, "language": language},
        format="json",
    )


def state(client, code, token):
    return client.get(f"{BASE}{code}/", HTTP_X_DUEL_TOKEN=token)


def answer(client, code, token, question_id, choice_id):
    return client.post(
        f"{BASE}{code}/answer/",
        {"question_id": question_id, "choice_id": choice_id},
        format="json",
        HTTP_X_DUEL_TOKEN=token,
    )


def right(question_id):
    return Choice.objects.get(question_id=question_id, is_correct=True).id


def wrong(question_id):
    return Choice.objects.filter(question_id=question_id, is_correct=False).first().id


def start(client):
    """Host + guest olusturur. (host_token, guest_token, code)"""
    h = create(client).json()
    g = join(client, h["code"]).json()
    return h["token"], g["token"], h["code"]


def test_create_returns_contract(client, pool):
    r = create(client)
    assert r.status_code == 201
    d = r.json()
    assert len(d["code"]) == 6 and d["code"].isupper()
    assert not set(d["code"]) & set("01OI")
    assert d["role"] == "host" and d["status"] == "waiting" and d["token"]
    assert d["total_questions"] == 10 and d["time_limit_seconds"] == 30
    assert d["expires_in_seconds"] == 1800


def test_waiting_state_then_join_starts_countdown(client, pool):
    with freeze_time("2026-01-01 10:00:00") as t:
        h = create(client, name="Ahmet").json()
        s = state(client, h["code"], h["token"]).json()
        assert s["status"] == "waiting" and s["phase"] == "waiting"
        assert s["opponent"]["name"] is None and s["question"] is None

        # kod buyuk/kucuk harf duyarsiz
        g = join(client, h["code"].lower(), name="Ali").json()
        assert g["role"] == "guest" and g["status"] == "active" and g["token"] != h["token"]

        s = state(client, h["code"], h["token"]).json()
        assert s["phase"] == "countdown" and 3000 <= s["starts_in_ms"] <= 4000
        assert s["opponent"]["name"] == "Ali" and s["question"] is None
        t.tick(timedelta(seconds=4))
        s = state(client, h["code"], h["token"]).json()
        assert s["phase"] == "question" and s["index"] == 0
        assert s["remaining_ms"] == 30000 and len(s["question"]["choices"]) == 4


def test_full_duel_host_wins(client, pool):
    with freeze_time("2026-01-01 10:00:00") as t:
        ht, gt, code = start(client)
        t.tick(timedelta(seconds=4))
        for i in range(10):
            s = state(client, code, ht).json()
            assert s["phase"] == "question" and s["index"] == i
            q = s["question"]["id"]
            assert "is_correct" not in str(s["question"])
            ra = answer(client, code, ht, q, right(q))
            assert ra.status_code == 200 and ra.json()["is_correct"] is True
            assert ra.json()["points"] == 150  # ayni anda cevap -> tam bonus
            # rakip henuz cevaplamadi: secimi ve puani gizli
            mid = state(client, code, gt).json()
            assert mid["opponent"]["answered"] is True
            assert mid["opponent"]["correct"] == i and mid["reveal"] is None
            rb = answer(client, code, gt, q, wrong(q))
            assert rb.json()["is_correct"] is False and rb.json()["points"] == 0

            rev = state(client, code, ht).json()
            assert rev["phase"] == "reveal"
            assert rev["reveal"]["correct_choice_id"] == right(q)
            assert rev["reveal"]["my_correct"] is True and rev["reveal"]["opponent_correct"] is False
            assert rev["reveal"]["opponent_choice_id"] == wrong(q)
            assert rev["me"]["correct"] == i + 1 and rev["opponent"]["correct"] == 0
            t.tick(timedelta(seconds=3))
        done = state(client, code, ht).json()
        assert done["status"] == "finished" and done["phase"] == "finished"
        assert done["result"]["winner"] == "me"
        assert done["result"]["me"] == {"correct": 10, "points": 1500}
        assert done["result"]["opponent"] == {"correct": 0, "points": 0}
        assert state(client, code, gt).json()["result"]["winner"] == "opponent"


def test_draw_when_equal(client, pool):
    with freeze_time("2026-01-01 10:00:00") as t:
        ht, gt, code = start(client)
        t.tick(timedelta(seconds=4))
        for _ in range(10):
            q = state(client, code, ht).json()["question"]["id"]
            answer(client, code, ht, q, right(q))
            answer(client, code, gt, q, right(q))
            t.tick(timedelta(seconds=3))
        res = state(client, code, ht).json()["result"]
        assert res["winner"] == "draw" and res["me"] == res["opponent"]


def test_more_points_breaks_tie_on_correct_count(client, pool):
    with freeze_time("2026-01-01 10:00:00") as t:
        ht, gt, code = start(client)
        t.tick(timedelta(seconds=4))
        for _ in range(10):
            q = state(client, code, ht).json()["question"]["id"]
            answer(client, code, ht, q, right(q))  # aninda: 150
            t.tick(timedelta(seconds=15))
            answer(client, code, gt, q, right(q))  # 15 sn sonra: 125
            t.tick(timedelta(seconds=3))
        res = state(client, code, ht).json()["result"]
        assert res["me"]["correct"] == res["opponent"]["correct"] == 10
        assert res["winner"] == "me" and res["me"]["points"] > res["opponent"]["points"]


def test_unanswered_round_advances_after_timeout(client, pool):
    with freeze_time("2026-01-01 10:00:00") as t:
        ht, gt, code = start(client)
        t.tick(timedelta(seconds=4))
        q = state(client, code, ht).json()["question"]["id"]
        answer(client, code, ht, q, right(q))
        # rakip cevap vermez: sure (30 sn + 1 sn tolerans) dolunca reveal
        t.tick(timedelta(seconds=30))
        assert state(client, code, ht).json()["phase"] == "question"
        t.tick(timedelta(seconds=2))
        s = state(client, code, ht).json()
        assert s["phase"] == "reveal" and s["reveal"]["opponent_choice_id"] is None
        assert s["reveal"]["opponent_correct"] is False
        # gec kalan cevap reddedilir
        late = answer(client, code, gt, q, right(q))
        assert late.status_code == 409 and late.json()["code"] == "round_over"
        t.tick(timedelta(seconds=3))
        assert state(client, code, ht).json()["index"] == 1


def test_nobody_answers_all_rounds_finish_by_polling_late(client, pool):
    with freeze_time("2026-01-01 10:00:00") as t:
        ht, gt, code = start(client)
        t.tick(timedelta(minutes=20))  # kimse yoklama yapmadi; tembel ilerleme hepsini gecer
        s = state(client, code, ht).json()
        assert s["status"] == "finished"
        assert s["result"]["winner"] == "draw"
        assert s["result"]["me"] == {"correct": 0, "points": 0}


def test_auth_and_not_found(client, pool):
    h = create(client).json()
    assert state(client, h["code"], "yanlis").status_code == 403
    assert client.get(f"{BASE}{h['code']}/").status_code == 403
    assert state(client, "ZZZZZZ", h["token"]).status_code == 404
    assert answer(client, h["code"], "yanlis", 1, 1).status_code == 403
    r = client.post(
        f"{BASE}ZZZZZZ/join/", {"player_id": str(uuid.uuid4()), "player_name": "Ali"}, format="json"
    )
    assert r.status_code == 404 and r.json()["code"] == "duel_not_found"
    # baska duellonun token'i gecmez
    h2 = create(client).json()
    assert state(client, h["code"], h2["token"]).status_code == 403


def test_cannot_join_own_duel(client, pool):
    me = uuid.uuid4()
    h = create(client, player=me).json()
    r = join(client, h["code"], player=me)
    assert r.status_code == 400 and r.json()["code"] == "same_player"
    assert Duel.objects.get(code=h["code"]).status == "waiting"


def test_full_and_finished_and_expired(client, pool):
    with freeze_time("2026-01-01 10:00:00") as t:
        h = create(client).json()
        join(client, h["code"])
        r = join(client, h["code"])
        assert r.status_code == 409 and r.json()["code"] == "duel_full"

        t.tick(timedelta(minutes=20))
        Duel.objects.filter(code=h["code"]).update(status="finished")
        r = join(client, h["code"])
        assert r.status_code == 409 and r.json()["code"] == "duel_finished"

        lonely = create(client).json()
        t.tick(timedelta(minutes=31))
        r = join(client, lonely["code"])
        assert r.status_code == 410 and r.json()["code"] == "duel_expired"
        assert state(client, lonely["code"], lonely["token"]).json()["status"] == "expired"


def test_answer_rules(client, pool):
    with freeze_time("2026-01-01 10:00:00") as t:
        ht, gt, code = start(client)
        # geri sayim sirasinda cevap yok
        r = answer(client, code, ht, 1, 1)
        assert r.status_code == 409 and r.json()["code"] == "not_active"
        t.tick(timedelta(seconds=4))
        q = state(client, code, ht).json()["question"]["id"]
        other = Question.objects.exclude(pk=q).first().id
        r = answer(client, code, ht, other, 1)
        assert r.status_code == 400 and r.json()["code"] == "wrong_question"
        r = answer(client, code, ht, q, 999999)
        assert r.status_code == 400 and r.json()["code"] == "invalid_choice"
        assert answer(client, code, ht, q, right(q)).status_code == 200
        r = answer(client, code, ht, q, right(q))
        assert r.status_code == 409 and r.json()["code"] == "already_answered"
        # null = sure doldu/bos
        r = answer(client, code, gt, q, None)
        assert r.status_code == 200 and r.json()["is_correct"] is False
        # reveal sirasinda yeni cevap kabul edilmez
        r = answer(client, code, ht, q, right(q))
        assert r.status_code == 409


def test_unapproved_and_empty_levels(client, category):
    for i in range(3):
        q = Question.objects.create(category=category, text=f"x{i}", level=1, is_approved=False)
        for j in range(4):
            Choice.objects.create(question=q, text=str(j), is_correct=j == 0)
    r = create(client)
    assert r.status_code == 409 and r.json()["code"] == "level_empty"
    make_questions(category, 1, 4)  # yalnizca 4 onayli soru
    d = create(client).json()
    assert d["total_questions"] == 4
    duel = Duel.objects.get(code=d["code"])
    assert set(duel.question_order) <= set(
        Question.objects.filter(is_approved=True).values_list("id", flat=True)
    )


def test_create_validation(client, pool):
    assert create(client, level=11).json()["code"] == "invalid_level"
    assert create(client, level=0).status_code == 400
    assert create(client, category="yok").status_code == 404
    r = create(client, name="a")
    assert r.status_code == 400 and r.json()["code"] == "invalid_name"
    r = create(client, name="siktir")
    assert r.status_code == 400 and r.json()["code"] == "invalid_name"
    r = join(client, create(client).json()["code"], name="<b>")
    assert r.status_code == 400 and r.json()["code"] == "invalid_name"
    # player_id zorunlu
    r = client.post(BASE, {"category": "siyer", "player_name": "Ahmet"}, format="json")
    assert r.status_code == 400


def test_level_lock_not_required_in_duel(client, category):
    make_questions(category, 5, 10)  # 1-4 bos, 5. seviye dolu
    assert create(client, level=5).status_code == 201


def test_each_player_sees_own_language_same_ids(client, pool):
    q = Question.objects.filter(level=1).first()
    ids = list(Choice.objects.filter(question=q).order_by("id").values_list("id", flat=True))
    QuestionTranslation.objects.create(
        question=q,
        language="uz",
        text="O'zbekcha savol",
        explanation="izoh",
        choice_1="A-uz",
        choice_2="B-uz",
        choice_3="C-uz",
        choice_4="D-uz",
    )
    Question.objects.exclude(pk=q.pk).update(level=2)  # duello yalnizca bu soruyu cekse
    with freeze_time("2026-01-01 10:00:00") as t:
        h = create(client, language="tr").json()
        g = join(client, h["code"], language="uz").json()
        t.tick(timedelta(seconds=4))
        sh = state(client, h["code"], h["token"]).json()["question"]
        sg = state(client, h["code"], g["token"]).json()["question"]
        assert sh["text"] == q.text and sg["text"] == "O'zbekcha savol"
        assert sh["id"] == sg["id"]
        assert [c["id"] for c in sh["choices"]] == [c["id"] for c in sg["choices"]]  # ayni sira
        assert {c["id"] for c in sg["choices"]} == set(ids)
        assert {c["text"] for c in sg["choices"]} == {"A-uz", "B-uz", "C-uz", "D-uz"}


def test_duel_does_not_touch_solo_progress_or_leaderboard(client, pool):
    with freeze_time("2026-01-01 10:00:00") as t:
        ht, gt, code = start(client)
        t.tick(timedelta(seconds=4))
        for _ in range(10):
            q = state(client, code, ht).json()["question"]["id"]
            answer(client, code, ht, q, right(q))
            answer(client, code, gt, q, right(q))
            t.tick(timedelta(seconds=3))
    assert QuizSession.objects.count() == 0 and LevelProgress.objects.count() == 0
    assert client.get("/api/v1/leaderboard/").json()["entries"] == []


def test_opponent_connected_flag(client, pool):
    with freeze_time("2026-01-01 10:00:00") as t:
        ht, gt, code = start(client)
        state(client, code, gt)  # konuk yoklama yapti
        assert state(client, code, ht).json()["opponent"]["connected"] is True
        t.tick(timedelta(seconds=11))
        assert state(client, code, ht).json()["opponent"]["connected"] is False
