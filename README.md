# DiniQuiz — Backend

Django + DRF + PostgreSQL REST API. Ürün kuralları ve API sözleşmesi: `docs/`.

## Yerel çalıştırma

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements/dev.txt
cp .env.example .env
docker compose up -d db
python manage.py migrate
python manage.py seed_categories
python manage.py load_questions fixtures/questions/ --approve
python manage.py createsuperuser
python manage.py runserver
pytest
```

Swagger: `/api/docs/` · Admin: `/yonetim/` · Sağlık: `/api/v1/health/`

> `fixtures/questions/` altındaki sorular **örnektir**. Yayından önce 20'şer soruya tamamlanmalı ve uzman onayından geçmelidir.

## Render'a dağıtım

1. Bu repoyu GitHub'a push'la.
2. Render → **New → Blueprint** → repoyu seç. `render.yaml` PostgreSQL (`diniquiz-db`) ve Docker web servisini (`diniquiz-backend`) oluşturur; `DATABASE_URL` ve `SECRET_KEY` otomatik gelir.
3. İlk deploy'da konteyner açılışta `migrate` + `seed_categories` çalıştırır.
4. Soruları yüklemek için bir kez `LOAD_QUESTIONS_ON_START=true` yapıp deploy et (sonra `false`'a çek), ya da Render Shell'den `python manage.py load_questions fixtures/questions/ --approve`.
5. Render Shell'den `python manage.py createsuperuser` ile admin oluştur.
6. Frontend yayınlanınca `CORS_ALLOWED_ORIGINS` değerini gerçek static site adresiyle güncelle (virgülle birden fazla).
7. `expire_sessions` için Render **Cron Job** (örn. `*/15 * * * *`, komut `python manage.py expire_sessions`) eklenebilir; zorunlu değil, süresi dolan oturumlar istek anında da kapatılır.

Not: Render free planında web servisi boştayken uyur, free PostgreSQL ise sınırlı süreli olabilir; kalıcı kullanım için ücretli plan seç.
