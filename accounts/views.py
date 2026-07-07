"""Module d'authentification Tchokos — email + mot de passe (JWT) + option OTP.

Endpoints (préfixe /api/auth/) :
  POST  login/            email + password  -> {access, refresh, user}
  POST  register/         inscription client -> {access, refresh, user}
  POST  token/refresh/    refresh -> nouvel access
  POST  logout/           blacklist du refresh
  GET   me/   PATCH me/   profil de l'utilisateur connecté
  POST  password/change/  ancien + nouveau mot de passe
  POST  password/reset/   demande (email envoyé avec lien)
  POST  password/reset/confirm/   uid + token + nouveau mot de passe
  POST  otp/request/      envoie un code par téléphone
  POST  otp/verify/       code -> {access, refresh, user}
"""
import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from . import otp as otp_lib
from .serializers import (
    ChangePasswordSerializer,
    EmailTokenObtainPairSerializer,
    OTPRequestSerializer,
    OTPVerifySerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    RegisterSerializer,
    UserSerializer,
)

logger = logging.getLogger(__name__)
User = get_user_model()


def _tokens_for(user):
    refresh = RefreshToken.for_user(user)
    return {
        "access": str(refresh.access_token),
        "refresh": str(refresh),
        "user": UserSerializer(user).data,
    }


class LoginView(TokenObtainPairView):
    """Login email + mot de passe (renvoie access, refresh, user)."""
    serializer_class = EmailTokenObtainPairSerializer
    permission_classes = [AllowAny]


@api_view(["POST"])
@permission_classes([AllowAny])
def register(request):
    serializer = RegisterSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    user = serializer.save()
    return Response(_tokens_for(user), status=status.HTTP_201_CREATED)


@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
def me(request):
    if request.method == "PATCH":
        serializer = UserSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
    return Response(UserSerializer(request.user).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def logout(request):
    """Invalide le refresh token (blacklist)."""
    token = request.data.get("refresh")
    if token:
        try:
            RefreshToken(token).blacklist()
        except Exception:  # token déjà invalide
            pass
    return Response(status=status.HTTP_205_RESET_CONTENT)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def change_password(request):
    serializer = ChangePasswordSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    user = request.user
    if not user.check_password(serializer.validated_data["old_password"]):
        return Response({"detail": "Ancien mot de passe incorrect."}, status=status.HTTP_400_BAD_REQUEST)
    user.set_password(serializer.validated_data["new_password"])
    user.save(update_fields=["password"])
    return Response({"detail": "Mot de passe mis à jour."})


@api_view(["POST"])
@permission_classes([AllowAny])
def password_reset_request(request):
    serializer = PasswordResetRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    email = serializer.validated_data["email"]
    user = User.objects.filter(email__iexact=email, is_active=True).first()
    # Réponse identique que l'email existe ou non (anti-énumération)
    if user:
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        link = f"{settings.FRONTEND_URL}/mot-de-passe-oublie/confirmer?uid={uid}&token={token}"
        try:
            send_mail(
                subject="Réinitialisation de votre mot de passe Tchokos",
                message=(
                    f"Bonjour,\n\nPour réinitialiser votre mot de passe, "
                    f"cliquez sur ce lien :\n{link}\n\n"
                    f"Si vous n'êtes pas à l'origine de cette demande, ignorez cet email.\n\n— Tchokos"
                ),
                from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
                recipient_list=[user.email],
                fail_silently=True,
            )
        except Exception as exc:
            logger.error("[reset] envoi email échoué: %s", exc)
    return Response({"detail": "Si un compte existe pour cet email, un lien a été envoyé."})


@api_view(["POST"])
@permission_classes([AllowAny])
def password_reset_confirm(request):
    serializer = PasswordResetConfirmSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    try:
        uid = force_str(urlsafe_base64_decode(serializer.validated_data["uid"]))
        user = User.objects.get(pk=uid)
    except (User.DoesNotExist, ValueError, TypeError, OverflowError):
        return Response({"detail": "Lien invalide."}, status=status.HTTP_400_BAD_REQUEST)
    if not default_token_generator.check_token(user, serializer.validated_data["token"]):
        return Response({"detail": "Lien expiré ou invalide."}, status=status.HTTP_400_BAD_REQUEST)
    user.set_password(serializer.validated_data["new_password"])
    user.save(update_fields=["password"])
    return Response({"detail": "Mot de passe réinitialisé. Vous pouvez vous connecter."})


def _norm_phone(phone: str) -> str:
    return (phone or "").replace(" ", "").lstrip("+")


@api_view(["POST"])
@permission_classes([AllowAny])
def otp_request(request):
    serializer = OTPRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    raw = serializer.validated_data["phone"]
    norm = _norm_phone(raw)
    from django.db.models import Q
    user = User.objects.filter(is_active=True).filter(
        Q(phone=raw) | Q(phone=norm) | Q(phone="237" + norm)
    ).first()
    if not user:
        return Response(
            {"detail": "Aucun compte associé à ce numéro."},
            status=status.HTTP_404_NOT_FOUND,
        )
    code = otp_lib.generate_otp(user)
    payload = {"detail": "Code envoyé par SMS/WhatsApp."}
    if settings.DEBUG:
        payload["dev_code"] = code  # confort de test en dev uniquement
    return Response(payload)


@api_view(["POST"])
@permission_classes([AllowAny])
def otp_verify(request):
    serializer = OTPVerifySerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    norm = _norm_phone(serializer.validated_data["phone"])
    from django.db.models import Q
    user = User.objects.filter(is_active=True).filter(
        Q(phone=serializer.validated_data["phone"]) | Q(phone=norm) | Q(phone="237" + norm)
    ).first()
    if not user or not otp_lib.verify_otp(user, serializer.validated_data["code"]):
        return Response({"detail": "Code incorrect ou expiré."}, status=status.HTTP_400_BAD_REQUEST)
    return Response(_tokens_for(user))
