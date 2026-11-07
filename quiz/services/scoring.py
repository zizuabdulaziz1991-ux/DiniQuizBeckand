from django.conf import settings


def calculate_points(elapsed_ms: int, is_correct: bool) -> int:
    """Doğru cevap: 100 + round(kalan_sn / 15 * 50). Aksi halde 0."""
    if not is_correct:
        return 0
    limit = settings.QUIZ_TIME_LIMIT_SECONDS
    remaining = max(0.0, limit - elapsed_ms / 1000)
    bonus = round(remaining / limit * settings.QUIZ_MAX_SPEED_BONUS)
    return settings.QUIZ_BASE_POINTS + bonus


def max_score(total_questions: int) -> int:
    return total_questions * (settings.QUIZ_BASE_POINTS + settings.QUIZ_MAX_SPEED_BONUS)
