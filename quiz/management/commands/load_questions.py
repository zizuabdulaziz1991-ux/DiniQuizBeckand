import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from quiz.models import Category, Choice, Question, QuestionTranslation


def _sync(obj, values: dict) -> bool:
    """Yalnızca değişen alanları yazar; değişiklik olduysa True döner."""
    changed = [f for f, v in values.items() if getattr(obj, f) != v]
    if not changed:
        return False
    for f in changed:
        setattr(obj, f, values[f])
    obj.save(update_fields=changed + (["updated_at"] if hasattr(obj, "updated_at") else []))
    return True


class Command(BaseCommand):
    help = (
        "JSON dosyalarından (veya klasöründen) soru yükler. Tekrar çalıştırmak güvenlidir: "
        "şık id'leri korunur, değişmeyen kayıtlara yazılmaz."
    )

    def add_arguments(self, parser):
        parser.add_argument("path", help="JSON dosyası veya klasör")
        parser.add_argument("--approve", action="store_true", help="Yüklenen soruları onayla")
        parser.add_argument("--dry-run", action="store_true", help="Sadece doğrula, kaydetme")

    def handle(self, *args, **opts):
        path = Path(opts["path"])
        files = sorted(path.glob("*.json")) if path.is_dir() else [path]
        if not files or not all(f.exists() for f in files):
            raise CommandError(f"Dosya bulunamadı: {path}")

        created = updated = unchanged = 0
        errors = []
        with transaction.atomic():
            for f in files:
                c, u, n, errs = self._load_file(f, opts["approve"])
                created += c
                updated += u
                unchanged += n
                errors += errs
            if errors:
                raise CommandError("\n".join(errors))
            if opts["dry_run"]:
                transaction.set_rollback(True)
        suffix = " (dry-run, kaydedilmedi)" if opts["dry_run"] else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"{created} eklendi, {updated} güncellendi, {unchanged} değişmedi{suffix}"
            )
        )

    def _load_file(self, f: Path, approve: bool):
        created = updated = unchanged = 0
        errors = []
        data = json.loads(f.read_text(encoding="utf-8"))
        try:
            category = Category.objects.get(slug=data["category"])
        except (KeyError, Category.DoesNotExist):
            return 0, 0, 0, [f"{f.name}: kategori bulunamadı ({data.get('category')})"]

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
            if not 1 <= q.get("level", 1) <= settings.QUIZ_LEVELS:
                errors.append(f"{where}: 'level' 1-{settings.QUIZ_LEVELS} arasında olmalı")
                continue

            question, was_created = Question.objects.get_or_create(
                category=category, text=q["text"]
            )
            values = {
                "arabic_text": q.get("arabic_text", ""),
                "explanation": q.get("explanation", ""),
                "source": q.get("source", ""),
                "difficulty": q.get("difficulty", 1),
                "level": q.get("level", 1),
            }
            if approve:
                values["is_approved"] = True
            changed = _sync(question, values)
            changed |= self._sync_choices(question, choices, correct)
            tr_changed, tr_errors = self._sync_translations(
                question, q.get("translations", {}), where
            )
            errors += tr_errors
            changed |= tr_changed

            if was_created:
                created += 1
            elif changed:
                updated += 1
            else:
                unchanged += 1
        return created, updated, unchanged, errors

    @staticmethod
    def _sync_choices(question, texts, correct) -> bool:
        """Şıkları konumuna göre (id sırası) yerinde günceller; id'ler korunur."""
        existing = list(question.choices.order_by("id"))
        changed = False
        for i, text in enumerate(texts):
            wanted = {"text": text, "is_correct": i == correct}
            if i < len(existing):
                changed |= _sync(existing[i], wanted)
            else:
                Choice.objects.create(question=question, **wanted)
                changed = True
        extra = existing[len(texts):]
        if extra:
            Choice.objects.filter(pk__in=[c.pk for c in extra]).delete()
            changed = True
        return changed

    @staticmethod
    def _sync_translations(question, translations, where):
        errors = []
        changed = False
        for lang, t in translations.items():
            if lang not in settings.QUIZ_LANGUAGES:
                errors.append(f"{where}: desteklenmeyen dil '{lang}'")
                continue
            choices = t.get("choices", [])
            if len(choices) != 4 or not t.get("text"):
                errors.append(f"{where} [{lang}]: çeviride metin ve 4 şık olmalı")
                continue
            values = {
                "text": t["text"],
                "explanation": t.get("explanation", ""),
                "choice_1": choices[0],
                "choice_2": choices[1],
                "choice_3": choices[2],
                "choice_4": choices[3],
            }
            obj, was_created = QuestionTranslation.objects.get_or_create(
                question=question, language=lang, defaults=values
            )
            changed |= was_created or _sync(obj, values)
        return changed, errors
