from datetime import timedelta

import pytest
from django.test import override_settings
from freezegun import freeze_time

from quiz.models import QuizSession
from quiz.services.scoring import calculate_points

BASE = "/api/v1"


def start(client, slug="siyer"):
    r = client.post(f"{BASE}/sessions/", {"category": slug, "platform": "web"}, format="json")
    assert r.status_code == 201, r.content
    return r.json()


def hdr(s):
    return {"HTTP_X_SESSION_TOKEN": s["token"]}


def current(client, s):
    return client.get(f"{BASE}/sessions/{s['session_id']}/current/", **hdr(s))


def answer(client, s, qid, cid):
    return client.post(
        f"{BASE}/sessions/{s['session_id']}/answer/",
        {"question_id": qid, "choice_id": cid},
        format="json",
        **hdr(s),
    )


def correct_id(question_id):
    from quiz.models import Choice

    return Choice.objects.get(question_id=question_id, is_correct=True).id


@pytest.mark.parametrize(
    "elapsed_ms,correct,expected",
    [(0, True, 150), (7500, True, 125), (15000, True, 100), (16500, True, 100), (0, False, 0)],
)
def test_scoring(elapsed_ms, correct, expected):
    assert calculate_points(elapsed_ms, correct) == expected


def test_start_and_current_hides_correct(client, questions):
    s = start(client)
    assert s["total_questions"] == 5
    body = current(client, s).json()
    assert "is_correct" not in str(body)
    assert len(body["question"]["choices"]) == 4
    assert body["remaining_ms"] <= 15000


def test_invalid_token_403(client, questions):
    s = start(client)
    r = client.get(f"{BASE}/sessions/{s['session_id']}/current/", HTTP_X_SESSION_TOKEN="x")
    assert r.status_code == 403


def test_refresh_does_not_reset_timer(client, questions):
    s = start(client)
    with freeze_time("2026-01-01 10:00:00") as t:
        current(client, s)
        t.tick(timedelta(seconds=5))
        body = current(client, s).json()
    assert 9000 <= body["remaining_ms"] <= 10000


def test_full_flow_and_leaderboard(client, questions):
    s = start(client)
    for _ in range(5):
        q = current(client, s).json()["question"]
        r = answer(client, s, q["id"], correct_id(q["id"]))
        assert r.status_code == 200
        assert r.json()["is_correct"] is True
    assert r.json()["is_last"] is True
    assert current(client, s).status_code == 409

    res = client.get(f"{BASE}/sessions/{s['session_id']}/result/", **hdr(s)).json()
    assert res["correct_count"] == 5 and res["max_score"] == 750

    n = client.post(f"{BASE}/sessions/{s['session_id']}/name/", {"player_name": "  Ahmet "}, format="json", **hdr(s))
    assert n.status_code == 200 and n.json() == {"rank": 1, "in_top_10": True}
    again = client.post(f"{BASE}/sessions/{s['session_id']}/name/", {"player_name": "Ali"}, format="json", **hdr(s))
    assert again.status_code == 409

    lb = client.get(f"{BASE}/leaderboard/?category=siyer").json()
    assert lb["entries"][0]["player_name"] == "Ahmet"
    assert client.get(f"{BASE}/leaderboard/").json()["entries"][0]["rank"] == 1


def test_skip_and_double_answer(client, questions):
    s = start(client)
    q = current(client, s).json()["question"]
    other = next(x for x in questions if x.id != q["id"])
    assert answer(client, s, other.id, None).status_code == 400
    assert answer(client, s, q["id"], correct_id(q["id"])).status_code == 200
    assert answer(client, s, q["id"], correct_id(q["id"])).status_code == 409


def test_timeout_counts_as_empty(client, questions):
    s = start(client)
    with freeze_time("2026-01-01 10:00:00") as t:
        q = current(client, s).json()["question"]
        t.tick(timedelta(seconds=17))
        r = answer(client, s, q["id"], correct_id(q["id"])).json()
    assert r["is_correct"] is False and r["points"] == 0
    assert QuizSession.objects.get(pk=s["session_id"]).empty_count == 1


def test_wrong_answer_zero_points(client, questions):
    s = start(client)
    q = current(client, s).json()["question"]
    wrong = next(c["id"] for c in q["choices"] if c["id"] != correct_id(q["id"]))
    r = answer(client, s, q["id"], wrong).json()
    assert r["points"] == 0 and r["correct_choice_id"] == correct_id(q["id"])


def test_expired_session_410(client, questions):
    s = start(client)
    QuizSession.objects.filter(pk=s["session_id"]).update(started_at="2020-01-01T00:00:00Z")
    assert current(client, s).status_code == 410


@pytest.mark.parametrize("name", ["a", "x" * 21, "<script>", "siktir git"])
def test_bad_names(client, questions, name):
    s = start(client)
    for _ in range(5):
        q = current(client, s).json()["question"]
        answer(client, s, q["id"], None)
    r = client.post(f"{BASE}/sessions/{s['session_id']}/name/", {"player_name": name}, format="json", **hdr(s))
    assert r.status_code == 400


def test_name_before_finish_rejected(client, questions):
    s = start(client)
    r = client.post(f"{BASE}/sessions/{s['session_id']}/name/", {"player_name": "Ali"}, format="json", **hdr(s))
    assert r.status_code == 409


def test_unapproved_questions_excluded(client, category):
    from quiz.models import Question

    Question.objects.create(category=category, text="x", is_approved=False)
    assert client.post(f"{BASE}/sessions/", {"category": "siyer"}, format="json").status_code == 409


def test_health_and_categories(client, questions):
    assert client.get(f"{BASE}/health/").json() == {"status": "ok"}
    assert client.get(f"{BASE}/categories/").json()[0]["question_count"] == 5
