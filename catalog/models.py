from django.db import models
from django.db.models import Avg
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _


class TimeStamped(models.Model):
    created_at = models.DateTimeField(_("créé le"), auto_now_add=True)
    updated_at = models.DateTimeField(_("modifié le"), auto_now=True)

    class Meta:
        abstract = True


class Category(TimeStamped):
    """Catégorie de produits (chaussures, vêtements, accessoires…)."""

    name = models.CharField(_("nom"), max_length=120)
    slug = models.SlugField(_("slug"), max_length=140, unique=True, blank=True)
    description = models.TextField(_("description"), blank=True)
    image = models.ImageField(
        _("image"), upload_to="categories/", blank=True, null=True
    )
    image_url = models.URLField(
        _("image (URL externe)"), blank=True,
        help_text=_("Utilisée si aucune image n'est téléversée."),
    )
    order = models.PositiveIntegerField(_("ordre d'affichage"), default=0)
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        verbose_name = _("catégorie")
        verbose_name_plural = _("catégories")
        ordering = ["order", "name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    @property
    def product_count(self):
        return self.products.filter(is_active=True).count()


class Product(TimeStamped):
    """Produit mis en avant sur la vitrine."""

    class Target(models.TextChoices):
        FEMME = "femme", _("Femme")
        HOMME = "homme", _("Homme")
        ENFANT = "enfant", _("Enfant")
        UNISEXE = "unisexe", _("Unisexe")

    class Badge(models.TextChoices):
        NONE = "", _("Aucun")
        NOUVEAU = "nouveau", _("Nouveau")
        PROMO = "promo", _("Promo")
        BESTSELLER = "bestseller", _("Meilleure vente")
        MADE_IN_CMR = "made_in_cmr", _("Made in Cameroun")

    category = models.ForeignKey(
        Category,
        verbose_name=_("catégorie"),
        related_name="products",
        on_delete=models.PROTECT,
    )
    vendor = models.ForeignKey(
        "vendors.Vendor",
        verbose_name=_("vendeur"),
        related_name="products",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    name = models.CharField(_("nom"), max_length=200)
    slug = models.SlugField(_("slug"), max_length=220, unique=True, blank=True)
    brand = models.CharField(_("marque"), max_length=120, blank=True)
    description = models.TextField(_("description"), blank=True)

    price = models.DecimalField(
        _("prix (FCFA)"), max_digits=12, decimal_places=0,
        help_text=_("Prix de vente en francs CFA."),
    )
    compare_at_price = models.DecimalField(
        _("prix barré (FCFA)"), max_digits=12, decimal_places=0,
        blank=True, null=True,
        help_text=_("Ancien prix, affiché barré pour signaler une promo. Optionnel."),
    )

    target = models.CharField(
        _("cible"), max_length=10, choices=Target.choices,
        default=Target.UNISEXE,
    )
    badge = models.CharField(
        _("badge"), max_length=12, choices=Badge.choices, blank=True, default=""
    )

    image_url = models.URLField(
        _("image (URL externe)"), blank=True,
        help_text=_("Utilisée si aucune photo n'est téléversée. Pratique pour la démo."),
    )

    sku = models.CharField(_("référence (SKU)"), max_length=60, blank=True)
    stock_quantity = models.PositiveIntegerField(_("stock"), default=0)
    sizes = models.CharField(
        _("tailles disponibles"), max_length=200, blank=True,
        help_text=_("Liste libre séparée par des virgules, ex: 40, 41, 42."),
    )

    is_active = models.BooleanField(_("en ligne"), default=True)
    is_featured = models.BooleanField(_("mis en avant"), default=False)

    class Meta:
        verbose_name = _("produit")
        verbose_name_plural = _("produits")
        ordering = ["-is_featured", "-created_at"]
        indexes = [
            models.Index(fields=["is_active", "is_featured"]),
            models.Index(fields=["category", "is_active"]),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name)
            slug = base
            i = 2
            while Product.objects.exclude(pk=self.pk).filter(slug=slug).exists():
                slug = f"{base}-{i}"
                i += 1
            self.slug = slug
        super().save(*args, **kwargs)

    @property
    def in_stock(self):
        return self.stock_quantity > 0

    @property
    def discount_percent(self):
        if self.compare_at_price and self.compare_at_price > self.price:
            return round((1 - self.price / self.compare_at_price) * 100)
        return 0

    @property
    def primary_image(self):
        img = self.images.filter(is_primary=True).first() or self.images.first()
        return img

    @property
    def rating_avg(self):
        avg = self.reviews.filter(is_published=True).aggregate(a=Avg("rating"))["a"]
        return round(avg, 1) if avg else 0

    @property
    def rating_count(self):
        return self.reviews.filter(is_published=True).count()


class Review(models.Model):
    """Avis client sur un produit."""

    product = models.ForeignKey(
        Product, related_name="reviews", on_delete=models.CASCADE
    )
    author_name = models.CharField(_("nom du client"), max_length=120)
    rating = models.PositiveSmallIntegerField(_("note (1-5)"), default=5)
    comment = models.TextField(_("commentaire"), blank=True)
    is_published = models.BooleanField(_("publié"), default=True)
    created_at = models.DateTimeField(_("date"), auto_now_add=True)

    class Meta:
        verbose_name = _("avis")
        verbose_name_plural = _("avis")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.author_name} — {self.rating}★ ({self.product.name})"


class ProductImage(models.Model):
    product = models.ForeignKey(
        Product, related_name="images", on_delete=models.CASCADE
    )
    image = models.ImageField(_("image"), upload_to="products/")
    alt = models.CharField(_("texte alternatif"), max_length=200, blank=True)
    is_primary = models.BooleanField(_("image principale"), default=False)
    order = models.PositiveIntegerField(_("ordre"), default=0)

    class Meta:
        verbose_name = _("photo produit")
        verbose_name_plural = _("photos produit")
        ordering = ["-is_primary", "order", "id"]

    def __str__(self):
        return f"Photo de {self.product.name}"
