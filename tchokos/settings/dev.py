from .base import *

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = "django-insecure-*&^*x)z%uwwk_jbpa)fs83j&2xg7a)+k(!_14cb5pbhd5zfqr!"

# SECURITY WARNING: define the correct hosts in production!
ALLOWED_HOSTS = ["*"]

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Dev : autorise toute origine (aperçu mobile via IP LAN, ex. http://10.137.226.210:3000)
# En prod, CORS_ALLOWED_ORIGINS reste piloté par l'env dans base.py.
CORS_ALLOW_ALL_ORIGINS = True
CSRF_TRUSTED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://10.137.226.210:3000",
]


try:
    from .local import *
except ImportError:
    pass
