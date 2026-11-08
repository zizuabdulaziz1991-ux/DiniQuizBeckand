import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from django.conf import settings

from quiz.models import Category, Choice, Question, QuestionTranslation


class Command(BaseCommand):
    help = "JSON dosyalarından (veya klasöründen) soru yükler."

    def add_arguments(self, parser):
        parser.add_argument("path", help="JSON dosyası veya klasör")
        parser.add_argument("--approve", action="store_true", help="Yüklenen soruları onayla")
        parser.add_argument("--dry-run", action="store_true", help="Sadece doğrula, kaydetme")

    def handle(self, *args, **opts):
        path = Path(opts["path"])
        files = sorted(path.glob("*.json")) if path.is_dir() else [path]
        if not files or not all(f.exists() for f in files):
            raise CommandError(f"Dosya bulunamadı: {path}")

        created = updated = 0
        errors = []
        try:
            with transaction.atomic():
                for f in files:
                    c, u, errs = self._load_file(f, opts["approve"])
                    created += c
                    updated += u
                    errors += errs
                if errors:
                    raise CommandError("\n".join(errors))
                if opts["dry_run"]:
                    transaction.set_rollback(True)
        except CommandError:
            raise
        suffix = " (dry-run, kaydedilmedi)" if opts["dry_run"] else ""
        self.stdout.write(self.style.SUCCESS(f"{created} eklendi, {updated} güncellendi{suffix}"))

    def _load_file(self, f: Path, approve: bool):
        created = updated = 0
        errors = []
        data = json.loads(f.read_text(encoding="utf-8"))
        try:
            category = Category.objects.get(slug=data["category"])
        except (KeyError, Category.DoesNotExist):
            return 0, 0, [f"{f.name}: kategori bulunamadı ({data.get('category')})"]

        for n, q in enumerate(data.get("questions", []), start=1):
            where = f"{f.name} #{n}"
            choices = q.get("choices", [])
            correct = q.get("correct")
            if len(choices) != 4:
                errors.append(f"{where}: 4 şık olmalı")
                continue
            if not isinstance(correct, int) or not 0 <= correct < 4:
                errors.append(f"{where}: 'correct' 0-3 arasında olmalı")
                continue
            if not q.get("text"):
                errors.append(f"{where}: soru metni boş")
                continue

            question, was_created = Question.objects.get_or_create(
                category=category, text=q["text"]
            )
            question.arabic_text = q.get("arabic_text", "")
            question.explanation = q.get("explanation", "")
            question.source = q.get("source", "")
            question.difficulty = q.get("difficulty", 1)
            if approve:
                question.is_approved = True
            question.save()
            question.choices.all().delete()
            Choice.objects.bulk_create(
                Choice(question=question, text=t, is_correct=(i == correct))
                for i, t in enumerate(choices)
            )
            errors += self._load_translations(question, q.get("translations", {}), where)
            if was_created:
                created += 1
            else:
                updated += 1
        return created, updated, errors

    def _load_translations(self, question, translations, where):
        errors = []
        for lang, t in translations.items():
            if lang not in settings.QUIZ_LANGUAGES:
                errors.append(f"{where}: desteklenmeyen dil '{lang}'")
                continue
            choices = t.get("choices", [])
            if len(choices) != 4 or not t.get("text"):
                errors.append(f"{where} [{lang}]: çeviride metin ve 4 şık olmalı")
                continue
            QuestionTranslation.objects.update_or_create(
                question=question,
                language=lang,
                defaults={
                    "text": t["text"],
                    "explanation": t.get("explanation", ""),
                    "choice_1": choices[0],
                    "choice_2": choices[1],
                    "choice_3": choices[2],
                    "choice_4": choices[3],
                },
            )
        return errors
