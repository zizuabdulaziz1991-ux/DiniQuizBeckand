#!/bin/sh
set -e

python manage.py migrate --noinput
python manage.py seed_categories

# Örnek/ilk soruları yükle ve onayla (Render free planda Shell olmadığı için açılışta yapılır).
# İşin bitince LOAD_QUESTIONS_ON_START=false yapın.
if [ "${LOAD_QUESTIONS_ON_START:-false}" = "true" ]; then
  python manage.py load_questions fixtures/questions/ --approve
fi

# Admin kullanıcısı: DJANGO_SUPERUSER_USERNAME / _PASSWORD / _EMAIL tanımlıysa oluşturulur (varsa atlanır)
if [ -n "${DJANGO_SUPERUSER_USERNAME:-}" ] && [ -n "${DJANGO_SUPERUSER_PASSWORD:-}" ]; then
  python manage.py createsuperuser --noinput --email "${DJANGO_SUPERUSER_EMAIL:-admin@example.com}" || true
fi

exec gunicorn config.wsgi:application \
  --bind 0.0.0.0:${PORT:-10000} \
  --workers ${WEB_CONCURRENCY:-2} \
  --access-logfile -
