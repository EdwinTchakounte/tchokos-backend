"""Réglages de PRODUCTION — pilotés par variables d'environnement.

À activer via ``DJANGO_SETTINGS_MODULE=tchokos.settings.production`` (systemd /
gunicorn). Aucune valeur sensible n'est codée en dur : tout vient de l'env
(fichier ``.env`` à la racine du backend, chargé par ``base.py``, ou variables
injectées par systemd).

Variables attendues :
    SECRET_KEY                 clé Django (obligatoire)
    DATABASE_URL               ex. postgres://user:pass@127.0.0.1:5432/tchokos
    ALLOWED_HOSTS              ex. tchokos-sarl.com,www.tchokos-sarl.com,api.tchokos-sarl.com
    CSRF_TRUSTED_ORIGINS       ex. https://tchokos-sarl.com,https://api.tchokos-sarl.com
    CORS_ALLOWED_ORIGINS       ex. https://tchokos-sarl.com,https://www.tchokos-sarl.com
    PUBLIC_BASE_URL            https://api.tchokos-sarl.com  (webhook Tara)
    FRONTEND_URL               https://tchokos-sarl.com
    TARA_API_KEY / TARA_MERCHANT_ID / BREVO_API_KEY / SENDO_*  (cf. base.py)
"""
import dj_database_url

from .base import *  # noqa: F401,F403

DEBUG = False

# --- Sécurité de base ------------------------------------------------------
# SECRET_KEY doit venir de l'env en prod (base.py ne le définit pas).
SECRET_KEY = env("SECRET_KEY")  # noqa: F405 — vide → Django lève ImproperlyConfigured

# Hôtes autorisés (obligatoire quand DEBUG=False).
ALLOWED_HOSTS = env_list(  # noqa: F405
    "ALLOWED_HOSTS", "tchokos-sarl.com,www.tchokos-sarl.com,api.tchokos-sarl.com"
)

# --- Base de données : PostgreSQL via DATABASE_URL -------------------------
# Repli sur la config SQLite de base.py si DATABASE_URL n'est pas fourni
# (utile pour un `collectstatic` sans DB, mais la prod DOIT poser DATABASE_URL).
_database_url = env("DATABASE_URL")  # noqa: F405
if _database_url:
    DATABASES = {  # noqa: F405
        "default": dj_database_url.parse(_database_url, conn_max_age=600),
    }

# --- TLS terminé par nginx -------------------------------------------------
# nginx fait la terminaison HTTPS et transmet X-Forwarded-Proto ; Django doit
# reconnaître les requêtes comme sécurisées pour les cookies et les redirections.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
# Redirection HTTP→HTTPS gérée côté nginx par défaut ; activable ici via l'env.
SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", False)  # noqa: F405
SECURE_HSTS_SECONDS = int(env("SECURE_HSTS_SECONDS", "0"))  # noqa: F405 — passer à 31536000 quand tout est stable
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True

# Base publique Wagtail (liens dans l'admin / emails de notif).
WAGTAILADMIN_BASE_URL = env("PUBLIC_BASE_URL", "https://api.tchokos-sarl.com")  # noqa: F405

# Surcharges locales éventuelles (non versionnées).
try:
    from .local import *  # noqa: F401,F403
except ImportError:
    pass
