from django.conf import settings
from rest_framework import serializers

from catalog.models import Category, Product, ProductImage, Review
from orders.models import Order, OrderItem
from delivery.models import DeliveryZone


class DeliveryZoneSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeliveryZone
        fields = ["id", "name", "city", "fee", "eta_minutes"]


class CategorySerializer(serializers.ModelSerializer):
    image = serializers.SerializerMethodField()
    product_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Category
        fields = ["id", "name", "slug", "description", "image", "product_count", "order"]

    def get_image(self, obj):
        if obj.image:
            return self.context["request"].build_absolute_uri(obj.image.url)
        return obj.image_url or None


class ProductImageSerializer(serializers.ModelSerializer):
    image = serializers.SerializerMethodField()

    class Meta:
        model = ProductImage
        fields = ["id", "image", "alt", "is_primary"]

    def get_image(self, obj):
        if obj.image:
            return self.context["request"].build_absolute_uri(obj.image.url)
        return obj.image_url or None


class ReviewSerializer(serializers.ModelSerializer):
    class Meta:
        model = Review
        fields = ["id", "author_name", "rating", "comment", "created_at"]


class ProductListSerializer(serializers.ModelSerializer):
    category_slug = serializers.CharField(source="category.slug", read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True)
    image = serializers.SerializerMethodField()
    hover_image = serializers.SerializerMethodField()
    discount_percent = serializers.IntegerField(read_only=True)
    in_stock = serializers.BooleanField(read_only=True)
    rating_avg = serializers.ReadOnlyField()
    rating_count = serializers.ReadOnlyField()

    class Meta:
        model = Product
        fields = [
            "id", "name", "slug", "brand", "price", "compare_at_price",
            "discount_percent", "badge", "target", "in_stock",
            "rating_avg", "rating_count",
            "category_slug", "category_name", "image", "hover_image",
        ]

    def _img_url(self, img):
        if img.image:
            return self.context["request"].build_absolute_uri(img.image.url)
        return img.image_url or None

    def get_image(self, obj):
        img = obj.primary_image
        if img:
            return self._img_url(img)
        return obj.image_url or None

    def get_hover_image(self, obj):
        # 2e image de la galerie (pour l'effet de survol sur la carte)
        photos = list(obj.images.all())
        if len(photos) > 1:
            return self._img_url(photos[1])
        return None


class ProductDetailSerializer(ProductListSerializer):
    images = serializers.SerializerMethodField()
    sizes_list = serializers.SerializerMethodField()
    reviews = serializers.SerializerMethodField()

    class Meta(ProductListSerializer.Meta):
        fields = ProductListSerializer.Meta.fields + [
            "description", "sku", "stock_quantity", "sizes", "sizes_list",
            "images", "reviews",
        ]

    def get_reviews(self, obj):
        qs = obj.reviews.filter(is_published=True)[:20]
        return ReviewSerializer(qs, many=True).data

    def get_sizes_list(self, obj):
        return [s.strip() for s in obj.sizes.split(",") if s.strip()]

    def get_images(self, obj):
        photos = list(obj.images.all())
        if photos:
            return ProductImageSerializer(photos, many=True, context=self.context).data
        if obj.image_url:
            return [{"id": 0, "image": obj.image_url, "alt": obj.name, "is_primary": True}]
        return []


# ---- Commande (lead WhatsApp) ----

class OrderItemInputSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1, default=1)
    size = serializers.CharField(required=False, allow_blank=True, max_length=30)


class OrderCreateSerializer(serializers.Serializer):
    customer_name = serializers.CharField(max_length=150)
    phone = serializers.CharField(max_length=30)
    # Email obligatoire : sert à créer le compte client (canal Tara) et à tracer
    # la commande. Requis sur les deux canaux (WhatsApp et Tara).
    email = serializers.EmailField(required=True)
    city = serializers.CharField(max_length=120, required=False, allow_blank=True)
    address = serializers.CharField(max_length=255, required=False, allow_blank=True)
    note = serializers.CharField(required=False, allow_blank=True)
    zone_id = serializers.IntegerField(required=False, allow_null=True)
    items = OrderItemInputSerializer(many=True)
    # False = paiement direct Tara SANS livraison (retrait / pas d'expédition) :
    # on ne crée alors ni livraison interne ni colis Sendo.
    with_delivery = serializers.BooleanField(required=False, default=True)

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError("Le panier est vide.")
        return value


class ContactSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=150)
    email = serializers.EmailField(required=False, allow_blank=True)
    phone = serializers.CharField(max_length=30, required=False, allow_blank=True)
    message = serializers.CharField()


# ---- Espace client : « Mes commandes » + suivi colis Sendo ----

class MyOrderItemSerializer(serializers.ModelSerializer):
    line_total = serializers.IntegerField()

    class Meta:
        model = OrderItem
        fields = ["product_name", "size", "quantity", "unit_price", "line_total"]


class MyOrderSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    grand_total = serializers.IntegerField(read_only=True)
    items = MyOrderItemSerializer(many=True, read_only=True)
    tracking_url = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            "reference",
            "status",
            "status_display",
            "channel",
            "total",
            "delivery_fee",
            "grand_total",
            "city",
            "address",
            "created_at",
            "items",
            "sendo_status",
            "sendo_tracking_token",
            "tracking_url",
        ]

    def get_tracking_url(self, obj):
        """Lien vers la page publique de suivi Sendo (si un colis existe)."""
        base = getattr(settings, "SENDO_PUBLIC_URL", "") or ""
        if obj.sendo_tracking_token and base:
            return f"{base.rstrip('/')}/track/{obj.sendo_tracking_token}"
        return ""
