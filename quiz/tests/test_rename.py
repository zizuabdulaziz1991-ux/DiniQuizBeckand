import json
from io import StringIO

from django.core.management import call_command

from quiz.models import Choice, Question, QuestionTranslation

BASE_Q = {
    "text": "Eski soru metni?",
    "choices": ["A", "B", "C", "D"],
    "correct": 0,
    "explanation": "Aciklama",
    "level": 3,
    "translations": {
        "uz": {"text": "Eski savol?", "choices": ["a", "b", "c", "d"], "explanation": "izoh"}
    },
}


def write(tmp_path, q):
    p = tmp_path / "siyer.json"
    p.write_text(json.dumps({"category": "siyer", "questions": [q]}), encoding="utf-8")
    return str(p)


def load(path, *extra):
    out = StringIO()
    call_command("load_questions", path, *extra, stdout=out)
    return out.getvalue()


def test_renamed_from_keeps_id_and_approval(category, tmp_path):
    load(write(tmp_path, BASE_Q), "--approve")
    old = Question.objects.get()
    old_choice_ids = list(Choice.objects.order_by("id").values_list("id", flat=True))

    new = json.loads(json.dumps(BASE_Q))
    new["renamed_from"] = BASE_Q["text"]
    new["text"] = "Yeni soru metni?"
    new["translations"]["uz"]["text"] = "Yangi savol?"
    out = load(write(tmp_path, new), "--approve")

    assert "1 güncellendi" in out and "0 eklendi" in out
    q = Question.objects.get()  # kopya oluşmadı
    assert q.pk == old.pk and q.text == "Yeni soru metni?" and q.is_approved is True
    assert list(Choice.objects.order_by("id").values_list("id", flat=True)) == old_choice_ids
    assert QuestionTranslation.objects.get().text == "Yangi savol?"

    # ikinci yükleme: hiçbir şey değişmez
    assert "0 güncellendi, 1 değişmedi" in load(write(tmp_path, new), "--approve")
    assert Question.objects.count() == 1


def test_renamed_from_unknown_old_text_just_creates(category, tmp_path):
    new = json.loads(json.dumps(BASE_Q))
    new["renamed_from"] = "Hiç var olmayan metin?"
    load(write(tmp_path, new), "--approve")
    assert Question.objects.count() == 1 and Question.objects.get().text == BASE_Q["text"]
