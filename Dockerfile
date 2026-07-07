# ==========================================================================
#  Tchokos — image backend (Django/Wagtail + gunicorn) pour le VPS mutualisé.
#  - tourne en settings de PRODUCTION (DJANGO_SETTINGS_MODULE)
#  - statiques servis par WhiteNoise ; médias via volume monté dans le proxy
#  - migrate + collectstatic + gunicorn au démarrage (entrypoint)
#  - gunicorn écoute sur 0.0.0.0:8000 (joignable par le nginx central)
# ==========================================================================
FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000 \
    GUNICORN_WORKERS=3 \
    DJANGO_SETTINGS_MODULE=tchokos.settings.production

RUN useradd --create-home appuser

# Dépendances système (Pillow/WebP + psycopg/PostgreSQL)
RUN apt-get update --yes --quiet && apt-get install --yes --quiet --no-install-recommends \
      build-essential \
      libpq-dev \
      libjpeg62-turbo-dev \
      zlib1g-dev \
      libwebp-dev \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt   # gunicorn déjà épinglé dedans

COPY . /app

# Dossiers de données + droits ; entrypoint exécutable.
RUN mkdir -p /app/media /app/static \
 && chmod +x /app/deploy/entrypoint.sh \
 && chown -R appuser:appuser /app

USER appuser
EXPOSE 8000
ENTRYPOINT ["/app/deploy/entrypoint.sh"]
