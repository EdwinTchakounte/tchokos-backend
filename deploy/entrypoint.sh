#!/usr/bin/env sh
# Démarrage du backend Tchokos en production.
# migrate + collectstatic à chaud (le .env — SECRET_KEY, DATABASE_URL — est
# injecté par docker-compose), puis gunicorn sur 0.0.0.0:8000.
set -e

echo "→ Migrations base de données"
python manage.py migrate --noinput

echo "→ Collecte des fichiers statiques (WhiteNoise)"
python manage.py collectstatic --noinput

echo "→ Gunicorn sur 0.0.0.0:${PORT:-8000} (${GUNICORN_WORKERS:-3} workers)"
exec gunicorn tchokos.wsgi:application \
  --bind "0.0.0.0:${PORT:-8000}" \
  --workers "${GUNICORN_WORKERS:-3}" \
  --timeout 60 \
  --access-logfile - \
  --error-logfile -
