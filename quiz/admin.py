from django.contrib import admin
from django.core.exceptions import ValidationError
from django.forms.models import BaseInlineFormSet

from quiz.models import Category, Choice, Question, QuizSession, SessionAnswer


class ChoiceInlineFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        active = [
            f
            for f in self.forms
            if f.cleaned_data and not f.cleaned_data.get("DELETE") and f.cleaned_data.get("text")
        ]
        if len(active) != 4:
            raise ValidationError("Her sorunun tam olarak 4 şıkkı olmalıdır.")
        if sum(1 for f in active if f.cleaned_data.get("is_correct")) != 1:
            raise ValidationError("Tam olarak 1 doğru şık işaretlenmelidir.")


class ChoiceInline(admin.TabularInline):
    model = Choice
    formset = ChoiceInlineFormSet
    extra = 4
    max_num = 4


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "order", "is_active")
    prepopulated_fields = {"slug": ("name",)}


@admin.action(description="Seçili soruları onayla")
def approve_questions(modeladmin, request, queryset):
    queryset.update(is_approved=True)


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("text", "category", "difficulty", "is_approved")
    list_filter = ("category", "is_approved", "difficulty")
    search_fields = ("text", "source")
    inlines = [ChoiceInline]
    actions = [approve_questions]


@admin.action(description="Oyuncu adını sil (skor tablosundan kaldır)")
def clear_player_name(modeladmin, request, queryset):
    queryset.update(player_name="")


class SessionAnswerInline(admin.TabularInline):
    model = SessionAnswer
    extra = 0
    can_delete = False
    readonly_fields = ("question", "choice", "is_correct", "elapsed_ms", "points", "answered_at")

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(QuizSession)
class QuizSessionAdmin(admin.ModelAdmin):
    list_display = ("player_name", "category", "score", "status", "client_platform", "started_at")
    list_filter = ("status", "category", "client_platform")
    search_fields = ("player_name",)
    readonly_fields = ("id", "token", "question_order", "started_at", "finished_at")
    inlines = [SessionAnswerInline]
    actions = [clear_player_name]
