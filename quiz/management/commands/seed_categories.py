from django.core.management.base import BaseCommand

from quiz.models import Category, CategoryTranslation

CATEGORIES = [
    ("Genel İslami İlimler", "genel-islami-ilimler", "İman, ibadet, fıkıh ve hadis temelleri", "#6C5CE7", "book-open"),
    ("Siyer", "siyer", "Peygamber Efendimiz'in hayatı", "#FF8A3D", "moon-star"),
    ("İslam Tarihi", "islam-tarihi", "Dört Halife'den Osmanlı'ya", "#3D8BFF", "landmark"),
    ("Sahabe Hayatı", "sahabe-hayati", "Ashab-ı kiramın hayatı", "#00C2A8", "users"),
    ("Kur'an", "kuran", "Sureler, ayetler ve kıssalar", "#22B573", "book-heart"),
]


# Özbekçe kategori çevirileri (yayından önce ana dili Özbekçe olan biri kontrol etmeli)
UZ = {
    "genel-islami-ilimler": ("Umumiy islomiy ilmlar", "Iymon, ibodat, fiqh va hadis asoslari"),
    "siyer": ("Siyrat", "Payg'ambarimiz (s.a.v.) hayoti"),
    "islam-tarihi": ("Islom tarixi", "To'rt xalifadan Usmonlilargacha"),
    "sahabe-hayati": ("Sahobalar hayoti", "Sahobai kiromlar hayoti"),
    "kuran": ("Qur'on", "Suralar, oyatlar va qissalar"),
}


class Command(BaseCommand):
    help = "5 varsayılan kategoriyi oluşturur (idempotent)."

    def handle(self, *args, **opts):
        for order, (name, slug, desc, color, icon) in enumerate(CATEGORIES, start=1):
            category, _ = Category.objects.update_or_create(
                slug=slug,
                defaults={
                    "name": name,
                    "description": desc,
                    "color": color,
                    "icon": icon,
                    "order": order,
                    "is_active": True,
                },
            )
            name_uz, desc_uz = UZ[slug]
            CategoryTranslation.objects.update_or_create(
                category=category,
                language="uz",
                defaults={"name": name_uz, "description": desc_uz},
            )
        self.stdout.write(self.style.SUCCESS(f"{len(CATEGORIES)} kategori hazır"))
