#!/bin/sh
set -e

python manage.py migrate --noinput
python manage.py seed_categories

# İlk kurulumda soruları yükle (onaylı gelmez; admin panelinden onaylanır)
if [ "${LOAD_QUESTIONS_ON_START:-false}" = "true" ]; then
  python manage.py load_questions fixtures/questions/
fi

exec gunicorn config.wsgi:application \
  --bind 0.0.0.0:${PORT:-10000} \
  --workers ${WEB_CONCURRENCY:-2} \
  --access-logfile -
