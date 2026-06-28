from rest_framework import serializers

from catalog.models import Category, Product, ProductImage
from orders.models import Order, OrderItem


class CategorySerializer(serializers.ModelSerializer):
    image = serializers.SerializerMethodField()
    product_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Category
        fields = ["id", "name", "slug", "description", "image", "product_count", "order"]

    def get_image(self, obj):
        if obj.image:
            return self.context["request"].build_absolute_uri(obj.image.url)
        return None


class ProductImageSerializer(serializers.ModelSerializer):
    image = serializers.SerializerMethodField()

    class Meta:
        model = ProductImage
        fields = ["id", "image", "alt", "is_primary"]

    def get_image(self, obj):
        return self.context["request"].build_absolute_uri(obj.image.url)


class ProductListSerializer(serializers.ModelSerializer):
    category_slug = serializers.CharField(source="category.slug", read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True)
    image = serializers.SerializerMethodField()
    discount_percent = serializers.IntegerField(read_only=True)
    in_stock = serializers.BooleanField(read_only=True)

    class Meta:
        model = Product
        fields = [
            "id", "name", "slug", "brand", "price", "compare_at_price",
            "discount_percent", "badge", "target", "in_stock",
            "category_slug", "category_name", "image",
        ]

    def get_image(self, obj):
        img = obj.primary_image
        if img:
            return self.context["request"].build_absolute_uri(img.image.url)
        return None


class ProductDetailSerializer(ProductListSerializer):
    images = ProductImageSerializer(many=True, read_only=True)
    sizes_list = serializers.SerializerMethodField()

    class Meta(ProductListSerializer.Meta):
        fields = ProductListSerializer.Meta.fields + [
            "description", "sku", "stock_quantity", "sizes", "sizes_list", "images",
        ]

    def get_sizes_list(self, obj):
        return [s.strip() for s in obj.sizes.split(",") if s.strip()]


# ---- Commande (lead WhatsApp) ----

class OrderItemInputSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1, default=1)
    size = serializers.CharField(required=False, allow_blank=True, max_length=30)


class OrderCreateSerializer(serializers.Serializer):
    customer_name = serializers.CharField(max_length=150)
    phone = serializers.CharField(max_length=30)
    city = serializers.CharField(max_length=120, required=False, allow_blank=True)
    address = serializers.CharField(max_length=255, required=False, allow_blank=True)
    note = serializers.CharField(required=False, allow_blank=True)
    items = OrderItemInputSerializer(many=True)

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError("Le panier est vide.")
        return value


class ContactSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=150)
    email = serializers.EmailField(required=False, allow_blank=True)
    phone = serializers.CharField(max_length=30, required=False, allow_blank=True)
    message = serializers.CharField()
