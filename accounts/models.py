"""Modèle utilisateur unifié de Tchokos.

Identifiant de connexion = **email** + mot de passe (hashé par Django).
Option de connexion par **téléphone** (OTP) pour le marché camerounais.

Rôles : client / livreur / admin. Le livreur a un profil dédié
(``delivery.Courier``) lié en OneToOne. L'admin (is_staff) gère le catalogue
via le CMS et l'admin Django/Wagtail.
"""
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra):
        if not email:
            raise ValueError("L'email est obligatoire.")
        email = self.normalize_email(email)
        # Normalise le téléphone vide en None (l'unicité tolère plusieurs NULL)
        if not extra.get("phone"):
            extra["phone"] = None
        user = self.model(email=email, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        extra.setdefault("role", User.Role.CLIENT)
        return self._create_user(email, password, **extra)

    def create_superuser(self, email, password, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        extra.setdefault("role", User.Role.ADMIN)
        if extra.get("is_staff") is not True or extra.get("is_superuser") is not True:
            raise ValueError("Un superuser doit avoir is_staff=is_superuser=True.")
        return self._create_user(email, password, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    class Role(models.TextChoices):
        CLIENT = "client", _("Client")
        COURIER = "courier", _("Livreur")
        ADMIN = "admin", _("Admin")

    email = models.EmailField(_("email"), unique=True)
    full_name = models.CharField(_("nom complet"), max_length=150, blank=True)
    phone = models.CharField(
        _("téléphone"), max_length=30, unique=True, null=True, blank=True,
        help_text=_("Optionnel — permet la connexion / l'OTP par téléphone."),
    )
    role = models.CharField(
        _("rôle"), max_length=12, choices=Role.choices, default=Role.CLIENT
    )

    is_active = models.BooleanField(_("actif"), default=True)
    is_staff = models.BooleanField(
        _("équipe (accès admin)"), default=False,
        help_text=_("Accès au CMS produits et à l'admin Django/Wagtail."),
    )
    date_joined = models.DateTimeField(_("inscrit le"), default=timezone.now)

    # Connexion par téléphone (OTP) — code « envoyé » par SMS/WhatsApp en prod
    otp_code = models.CharField(_("code OTP"), max_length=6, blank=True)
    otp_expires_at = models.DateTimeField(_("OTP expire le"), null=True, blank=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []  # email + password demandés par défaut

    class Meta:
        verbose_name = _("utilisateur")
        verbose_name_plural = _("utilisateurs")
        ordering = ["-date_joined"]

    def __str__(self):
        return self.email

    @property
    def is_admin_role(self) -> bool:
        return self.role == self.Role.ADMIN or self.is_staff
