from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from quiz.models import QuizSession


class Command(BaseCommand):
    help = "TTL süresini aşan aktif oturumları 'expired' yapar."

    def handle(self, *args, **opts):
        cutoff = timezone.now() - timedelta(minutes=settings.QUIZ_SESSION_TTL_MINUTES)
        n = QuizSession.objects.filter(
            status=QuizSession.Status.ACTIVE, started_at__lt=cutoff
        ).update(status=QuizSession.Status.EXPIRED)
        self.stdout.write(self.style.SUCCESS(f"{n} oturum süresi doldu olarak işaretlendi"))
