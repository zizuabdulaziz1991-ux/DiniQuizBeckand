import secrets
import uuid

from django.core.exceptions import ValidationError
from django.db import models

from quiz.validators import validate_language


def generate_token():
    return secrets.token_urlsafe(32)


class Category(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    color = models.CharField(max_length=7, default="#6C5CE7")
    icon = models.CharField(max_length=50, blank=True)
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["order", "id"]
        verbose_name = "Kategori"
        verbose_name_plural = "Kategoriler"

    def __str__(self):
        return self.name


class Question(models.Model):
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name="questions")
    text = models.TextField()
    arabic_text = models.TextField(blank=True)
    explanation = models.TextField(blank=True)
    source = models.CharField(max_length=255, blank=True)
    difficulty = models.PositiveSmallIntegerField(default=1)
    level = models.PositiveSmallIntegerField(default=1, db_index=True)
    is_approved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["id"]
        verbose_name = "Soru"
        verbose_name_plural = "Sorular"

    def __str__(self):
        return self.text[:60]


class Choice(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="choices")
    text = models.CharField(max_length=255)
    is_correct = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Şık"
        verbose_name_plural = "Şıklar"

    def __str__(self):
        return self.text


class QuizSession(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Aktif"
        FINISHED = "finished", "Bitti"
        EXPIRED = "expired", "Süresi doldu"

    class Platform(models.TextChoices):
        WEB = "web", "Web"
        ANDROID = "android", "Android"
        IOS = "ios", "iOS"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    token = models.CharField(max_length=64, default=generate_token, editable=False)
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name="sessions")
    question_order = models.JSONField(default=list)
    current_index = models.PositiveSmallIntegerField(default=0)
    current_served_at = models.DateTimeField(null=True, blank=True)
    score = models.PositiveIntegerField(default=0)
    correct_count = models.PositiveSmallIntegerField(default=0)
    wrong_count = models.PositiveSmallIntegerField(default=0)
    empty_count = models.PositiveSmallIntegerField(default=0)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    player_name = models.CharField(max_length=20, blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    client_platform = models.CharField(max_length=20, choices=Platform.choices, default=Platform.WEB)
    language = models.CharField(max_length=5, default="tr")
    level = models.PositiveSmallIntegerField(default=1)
    player_id = models.UUIDField(null=True, blank=True, db_index=True)
    newly_unlocked = models.BooleanField(default=False)

    class Meta:
        ordering = ["-started_at"]
        verbose_name = "Quiz oturumu"
        verbose_name_plural = "Quiz oturumları"
        indexes = [
            models.Index(fields=["status", "-score", "finished_at"], name="lb_overall_idx"),
            models.Index(fields=["category", "status", "-score"], name="lb_category_idx"),
        ]

    def __str__(self):
        return f"{self.category.slug} · {self.player_name or 'anonim'} · {self.score}"


class SessionAnswer(models.Model):
    session = models.ForeignKey(QuizSession, on_delete=models.CASCADE, related_name="answers")
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    choice = models.ForeignKey(Choice, null=True, blank=True, on_delete=models.SET_NULL)
    is_correct = models.BooleanField(default=False)
    elapsed_ms = models.PositiveIntegerField(default=0)
    points = models.PositiveSmallIntegerField(default=0)
    answered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["session", "question"], name="uniq_session_question")
        ]
        verbose_name = "Cevap"
        verbose_name_plural = "Cevaplar"


class PlayerScore(QuizSession):
    """Admin'de oyuncu bazlı toplam skor ekranı için proxy model (tablo oluşturmaz)."""

    class Meta:
        proxy = True
        verbose_name = "Oyuncu skoru"
        verbose_name_plural = "Oyuncu skorları (toplam)"


class CategoryTranslation(models.Model):
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name="translations")
    language = models.CharField(max_length=5, validators=[validate_language])
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["category", "language"], name="uniq_category_language")
        ]
        verbose_name = "Kategori çevirisi"
        verbose_name_plural = "Kategori çevirileri"


class QuestionTranslation(models.Model):
    """Şıklar, Türkçe şıkların id sırasıyla (1. 2. 3. 4.) eşleşir. Boş bırakılan alan Türkçe'ye düşer."""

    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="translations")
    language = models.CharField(max_length=5, validators=[validate_language])
    text = models.TextField()
    explanation = models.TextField(blank=True)
    choice_1 = models.CharField(max_length=255, blank=True)
    choice_2 = models.CharField(max_length=255, blank=True)
    choice_3 = models.CharField(max_length=255, blank=True)
    choice_4 = models.CharField(max_length=255, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["question", "language"], name="uniq_question_language")
        ]
        verbose_name = "Soru çevirisi"
        verbose_name_plural = "Soru çevirileri"

    @property
    def choice_texts(self):
        return [self.choice_1, self.choice_2, self.choice_3, self.choice_4]


class LevelProgress(models.Model):
    """Anonim oyuncu (istemcinin ürettiği UUID) için kategori/seviye ilerlemesi."""

    player_id = models.UUIDField(db_index=True)
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name="progress")
    level = models.PositiveSmallIntegerField()
    passed = models.BooleanField(default=False)
    best_correct = models.PositiveSmallIntegerField(default=0)
    attempts = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["player_id", "category", "level"], name="uniq_player_category_level"
            )
        ]
        verbose_name = "Seviye ilerlemesi"
        verbose_name_plural = "Seviye ilerlemeleri"

    def __str__(self):
        return f"{self.player_id} · {self.category.slug} · L{self.level} · {'✓' if self.passed else '…'}"


def generate_duel_code():
    # 0/O/1/I gibi karışan karakterler yok
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(6))


class Duel(models.Model):
    """İki kişilik canlı yarış: aynı sorular, kilit adımlı (lock-step) turlar."""

    class Status(models.TextChoices):
        WAITING = "waiting", "Rakip bekleniyor"
        ACTIVE = "active", "Devam ediyor"
        FINISHED = "finished", "Bitti"
        EXPIRED = "expired", "Süresi doldu"

    code = models.CharField(max_length=6, unique=True, default=generate_duel_code)
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name="duels")
    level = models.PositiveSmallIntegerField(default=1)
    question_order = models.JSONField(default=list)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.WAITING)
    created_at = models.DateTimeField(auto_now_add=True)
    starts_at = models.DateTimeField(null=True, blank=True)
    index = models.PositiveSmallIntegerField(default=0)
    round_started_at = models.DateTimeField(null=True, blank=True)
    reveal_until = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Düello"
        verbose_name_plural = "Düellolar"

    def __str__(self):
        return f"{self.code} · {self.category.slug} · L{self.level} · {self.status}"


class DuelPlayer(models.Model):
    class Role(models.TextChoices):
        HOST = "host", "Kurucu"
        GUEST = "guest", "Konuk"

    duel = models.ForeignKey(Duel, on_delete=models.CASCADE, related_name="players")
    role = models.CharField(max_length=5, choices=Role.choices)
    player_id = models.UUIDField()
    name = models.CharField(max_length=20)
    token = models.CharField(max_length=64, default=generate_token, editable=False)
    language = models.CharField(max_length=5, default="tr")
    last_seen = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["duel", "role"], name="uniq_duel_role"),
        ]
        verbose_name = "Düello oyuncusu"
        verbose_name_plural = "Düello oyuncuları"

    def __str__(self):
        return f"{self.duel.code} · {self.role} · {self.name}"


class DuelAnswer(models.Model):
    duel = models.ForeignKey(Duel, on_delete=models.CASCADE, related_name="answers")
    player = models.ForeignKey(DuelPlayer, on_delete=models.CASCADE, related_name="answers")
    index = models.PositiveSmallIntegerField()
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    choice = models.ForeignKey(Choice, null=True, blank=True, on_delete=models.SET_NULL)
    is_correct = models.BooleanField(default=False)
    elapsed_ms = models.PositiveIntegerField(default=0)
    points = models.PositiveSmallIntegerField(default=0)
    answered_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["duel", "player", "index"], name="uniq_duel_player_round")
        ]
        verbose_name = "Düello cevabı"
        verbose_name_plural = "Düello cevapları"
