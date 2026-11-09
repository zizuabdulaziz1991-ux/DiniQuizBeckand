import uuid

import pytest

from quiz.models import Category, Choice, LevelProgress, Question

BASE = "/api/v1"


def make_questions(category, level, n=10):
    out = []
    for i in range(n):
        q = Question.objects.create(
            category=category, text=f"L{level}-S{i}", level=level, is_approved=True
        )
        for j in range(4):
            Choice.objects.create(question=q, text=f"Şık {j}", is_correct=(j == 0))
        out.append(q)
    return out


@pytest.fixture
def levels(category):
    """Seviye 1 ve 2 dolu (10'ar soru), 3+ boş."""
    make_questions(category, 1)
    make_questions(category, 2)
    return category


def start(client, level=1, player=None, **extra):
    body = {"category": "siyer", "level": level, **extra}
    headers = {"HTTP_X_PLAYER_ID": str(player)} if player else {}
    return client.post(f"{BASE}/sessions/", body, format="json", **headers)


def play(client, session, perfect=True):
    hdr = {"HTTP_X_SESSION_TOKEN": session["token"]}
    last = None
    for _ in range(session["total_questions"]):
        cur = client.get(f"{BASE}/sessions/{session['session_id']}/current/", **hdr).json()
        q = cur["question"]
        right = Choice.objects.get(question_id=q["id"], is_correct=True).id
        wrong = next(c["id"] for c in q["choices"] if c["id"] != right)
        last = client.post(
            f"{BASE}/sessions/{session['session_id']}/answer/",
            {"question_id": q["id"], "choice_id": right if perfect else wrong},
            format="json",
            **hdr,
        ).json()
    res = client.get(f"{BASE}/sessions/{session['session_id']}/result/", **hdr).json()
    return last, res


def level_map(client, player=None):
    headers = {"HTTP_X_PLAYER_ID": str(player)} if player else {}
    data = client.get(f"{BASE}/categories/siyer/levels/", **headers).json()
    return data, {row["level"]: row["status"] for row in data["levels"]}


def test_quiz_has_ten_questions(client, levels):
    r = start(client)
    assert r.status_code == 201
    assert r.json()["total_questions"] == 10 and r.json()["level"] == 1


def test_new_player_sees_level1_unlocked_others_locked_or_empty(client, levels):
    data, st = level_map(client, uuid.uuid4())
    assert data["level_count"] == 10 and data["questions_per_level"] == 10
    assert st[1] == "unlocked" and st[2] == "locked"
    assert all(st[n] == "empty" for n in range(3, 11))
    # kimliksiz istek de aynı görünür
    _, st2 = level_map(client)
    assert st2[1] == "unlocked" and st2[2] == "locked"


def test_locked_level_is_rejected(client, levels):
    p = uuid.uuid4()
    r = start(client, level=2, player=p)
    assert r.status_code == 403 and r.json()["code"] == "level_locked"
    assert start(client, level=2).status_code == 403  # kimliksiz de kilitli


def test_empty_level_and_invalid_level(client, levels):
    p = uuid.uuid4()
    LevelProgress.objects.create(player_id=p, category=levels, level=1, passed=True)
    LevelProgress.objects.create(player_id=p, category=levels, level=2, passed=True)
    r = start(client, level=3, player=p)
    assert r.status_code == 409 and r.json()["code"] == "level_empty"
    r = start(client, level=11, player=p)
    assert r.status_code == 400 and r.json()["code"] == "invalid_level"
    assert start(client, level=0, player=p).status_code == 400


def test_perfect_run_unlocks_next_level_once(client, levels):
    p = uuid.uuid4()
    s = start(client, level=1, player=p).json()
    last, res = play(client, s, perfect=True)
    for body in (last, res):
        assert body["perfect"] is True and body["level_passed"] is True
        assert body["level"] == 1 and body["next_level"] == 2
        assert body["newly_unlocked"] is True
    assert res["total_questions"] == 10

    _, st = level_map(client, p)
    assert st[1] == "completed" and st[2] == "unlocked" and st[3] == "empty"
    assert start(client, level=2, player=p).status_code == 201

    # tekrar oynamada 'yeni açıldı' tekrar gelmez
    s2 = start(client, level=1, player=p).json()
    _, res2 = play(client, s2, perfect=True)
    assert res2["perfect"] is True and res2["newly_unlocked"] is False
    assert res2["next_level"] == 2


def test_imperfect_run_does_not_unlock(client, levels):
    p = uuid.uuid4()
    s = start(client, level=1, player=p).json()
    _, res = play(client, s, perfect=False)
    assert res["perfect"] is False and res["level_passed"] is False
    assert res["next_level"] is None and res["newly_unlocked"] is False
    _, st = level_map(client, p)
    assert st[1] == "unlocked" and st[2] == "locked"
    row = LevelProgress.objects.get(player_id=p, level=1)
    assert row.attempts == 1 and row.best_correct == 0 and row.passed is False
    assert start(client, level=2, player=p).status_code == 403


def test_progress_is_per_player_and_per_category(client, levels):
    a, b = uuid.uuid4(), uuid.uuid4()
    play(client, start(client, level=1, player=a).json(), perfect=True)
    assert start(client, level=2, player=b).status_code == 403  # başkasının ilerlemesi geçmez

    other = Category.objects.create(name="Kur'an", slug="kuran")
    make_questions(other, 1)
    make_questions(other, 2)
    r = client.post(
        f"{BASE}/sessions/",
        {"category": "kuran", "level": 2},
        format="json",
        HTTP_X_PLAYER_ID=str(a),
    )
    assert r.status_code == 403  # siyer ilerlemesi kuran'ı açmaz


def test_last_level_has_no_next(client, levels):
    p = uuid.uuid4()
    for lv in range(1, 10):
        LevelProgress.objects.create(player_id=p, category=levels, level=lv, passed=True)
    make_questions(levels, 10)
    s = start(client, level=10, player=p).json()
    _, res = play(client, s, perfect=True)
    assert res["perfect"] is True and res["next_level"] is None
    assert res["newly_unlocked"] is False


def test_bad_player_header_is_ignored(client, levels):
    r = client.get(f"{BASE}/categories/siyer/levels/", HTTP_X_PLAYER_ID="not-a-uuid")
    assert r.status_code == 200
    assert client.get(f"{BASE}/categories/yok/levels/").status_code == 404


def test_categories_list_has_level_count(client, levels):
    assert client.get(f"{BASE}/categories/").json()[0]["level_count"] == 10
