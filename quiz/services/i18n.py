"""Dil çözümleme ve çeviri yardımcıları. Eksik çeviri her zaman Türkçe'ye (kaynak metne) düşer."""

from django.conf import settings

from quiz.models import CategoryTranslation, Choice, Question, QuestionTranslation


def resolve_language(explicit: str | None = None, accept_language: str | None = None) -> str:
    """Önce açık parametre, sonra Accept-Language başlığı, sonra varsayılan dil."""
    supported = settings.QUIZ_LANGUAGES
    if explicit:
        code = explicit.strip().lower().split("-")[0]
        if code in supported:
            return code
    if accept_language:
        # "uz-UZ,uz;q=0.9,tr;q=0.8" → kalite sırasına göre ilk desteklenen dil
        candidates = []
        for part in accept_language.split(","):
            tag, _, q = part.strip().partition(";q=")
            try:
                weight = float(q) if q else 1.0
            except ValueError:
                weight = 0.0
            candidates.append((weight, tag.strip().lower().split("-")[0]))
        for _, code in sorted(candidates, key=lambda c: -c[0]):
            if code in supported:
                return code
    return settings.QUIZ_DEFAULT_LANGUAGE


def category_texts(categories, language: str) -> dict:
    """{category_id: (name, description)}; çeviri yoksa kayıt eklenmez."""
    if language == settings.QUIZ_DEFAULT_LANGUAGE:
        return {}
    rows = CategoryTranslation.objects.filter(language=language, category__in=categories)
    return {t.category_id: (t.name, t.description) for t in rows}


def translated_question(question: Question, language: str) -> dict:
    """Soru metni, açıklama ve {choice_id: metin} sözlüğü (çevrilmemiş alanlar Türkçe)."""
    choices = list(question.choices.all().order_by("id"))
    result = {
        "text": question.text,
        "explanation": question.explanation,
        "choices": {c.id: c.text for c in choices},
    }
    if language == settings.QUIZ_DEFAULT_LANGUAGE:
        return result
    tr = QuestionTranslation.objects.filter(question=question, language=language).first()
    if not tr:
        return result
    result["text"] = tr.text or question.text
    result["explanation"] = tr.explanation or question.explanation
    for choice, text in zip(choices, tr.choice_texts):
        if text:
            result["choices"][choice.id] = text
    return result
