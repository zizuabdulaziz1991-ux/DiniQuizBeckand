import json
from io import StringIO

import pytest
from django.core.management import call_command

from quiz.models import Choice, Question, QuestionTranslation

QUESTION = {
    "text": "Test sorusu?",
    "choices": ["A", "B", "C", "D"],
    "correct": 1,
    "explanation": "Açıklama",
    "source": "Kaynak",
    "difficulty": 1,
    "translations": {
        "uz": {
            "text": "Test savoli?",
            "choices": ["A-uz", "B-uz", "C-uz", "D-uz"],
            "explanation": "Izoh",
        }
    },
}


def write(tmp_path, question=None):
    path = tmp_path / "siyer.json"
    path.write_text(
        json.dumps({"category": "siyer", "questions": [question or QUESTION]}), encoding="utf-8"
    )
    return str(path)


def load(path, *extra):
    out = StringIO()
    call_command("load_questions", path, *extra, stdout=out)
    return out.getvalue()


def snapshot():
    return (
        list(Choice.objects.order_by("id").values_list("id", "text", "is_correct")),
        list(QuestionTranslation.objects.values_list("id", "language", "text")),
        Question.objects.count(),
    )


def test_second_load_keeps_choice_ids_and_does_not_duplicate(category, tmp_path):
    path = write(tmp_path)
    first = load(path, "--approve")
    assert "1 eklendi" in first
    before = snapshot()
    updated_at = Question.objects.get().updated_at

    second = load(path, "--approve")
    assert "0 eklendi, 0 güncellendi, 1 değişmedi" in second
    assert snapshot() == before  # şık id'leri, çeviri id'leri ve sayılar aynı
    assert len(before[0]) == 4 and len(before[1]) == 1
    assert Question.objects.get().updated_at == updated_at  # değişmeyen kayda yazılmadı


def test_changed_fixture_updates_in_place(category, tmp_path):
    load(write(tmp_path), "--approve")
    ids_before = list(Choice.objects.order_by("id").values_list("id", flat=True))

    changed = json.loads(json.dumps(QUESTION))
    changed["choices"][2] = "C yeni"
    changed["correct"] = 2
    changed["translations"]["uz"]["text"] = "Yangi savol?"
    out = load(write(tmp_path, changed), "--approve")
    assert "1 güncellendi" in out

    assert list(Choice.objects.order_by("id").values_list("id", flat=True)) == ids_before
    c = Choice.objects.order_by("id")
    assert [x.text for x in c][2] == "C yeni"
    assert [x.is_correct for x in c] == [False, False, True, False]
    assert QuestionTranslation.objects.count() == 1
    assert QuestionTranslation.objects.get().text == "Yangi savol?"


def test_session_in_progress_survives_reload(client, category, tmp_path):
    """Yeniden yükleme sırasında devam eden oturumun şık id'leri geçerli kalır."""
    path = write(tmp_path)
    load(path, "--approve")
    s = client.post("/api/v1/sessions/", {"category": "siyer"}, format="json").json()
    hdr = {"HTTP_X_SESSION_TOKEN": s["token"]}
    cur = client.get(f"/api/v1/sessions/{s['session_id']}/current/", **hdr).json()
    choice_id = cur["question"]["choices"][0]["id"]

    load(path, "--approve")  # deploy/yeniden başlatma simülasyonu

    r = client.post(
        f"/api/v1/sessions/{s['session_id']}/answer/",
        {"question_id": cur["question"]["id"], "choice_id": choice_id},
        format="json",
        **hdr,
    )
    assert r.status_code == 200


def test_dry_run_changes_nothing(category, tmp_path):
    load(write(tmp_path), "--dry-run")
    assert Question.objects.count() == 0
