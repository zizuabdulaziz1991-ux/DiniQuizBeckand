FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=config.settings.prod

WORKDIR /app

COPY requirements/base.txt requirements/base.txt
RUN pip install --no-cache-dir -r requirements/base.txt

COPY . .

# collectstatic için geçici anahtar (yalnızca build aşamasında)
RUN SECRET_KEY=build-only DATABASE_URL=sqlite:////tmp/build.db python manage.py collectstatic --noinput

RUN useradd --create-home appuser && chown -R appuser /app
USER appuser

EXPOSE 10000
CMD ["sh", "docker-entrypoint.sh"]
