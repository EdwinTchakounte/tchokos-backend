"""OTP par téléphone (option de connexion). En dev, le code est renvoyé dans
la réponse / imprimé en console. En prod : SMS ou WhatsApp Business.
"""
import secrets
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

OTP_TTL_MINUTES = 10


def generate_otp(user) -> str:
    code = f"{secrets.randbelow(1_000_000):06d}"
    user.otp_code = code
    user.otp_expires_at = timezone.now() + timedelta(minutes=OTP_TTL_MINUTES)
    user.save(update_fields=["otp_code", "otp_expires_at"])
    # TODO prod : envoyer par SMS/WhatsApp. En dev on log simplement.
    if settings.DEBUG:
        print(f"[OTP] {user.phone or user.email} -> {code}")
    return code


def verify_otp(user, code: str) -> bool:
    if not user.otp_code or not user.otp_expires_at:
        return False
    if timezone.now() > user.otp_expires_at:
        return False
    if not secrets.compare_digest(user.otp_code, str(code).strip()):
        return False
    # Code à usage unique
    user.otp_code = ""
    user.otp_expires_at = None
    user.save(update_fields=["otp_code", "otp_expires_at"])
    return True
