from django.contrib import admin
from django.utils.html import format_html

from .models import Category, Product, ProductImage


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "order", "product_count", "is_active")
    list_editable = ("order", "is_active")
    search_fields = ("name",)
    prepopulated_fields = {"slug": ("name",)}


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1
    fields = ("image", "preview", "is_primary", "alt", "order")
    readonly_fields = ("preview",)

    @admin.display(description="Aperçu")
    def preview(self, obj):
        if obj and obj.image:
            return format_html(
                '<img src="{}" style="height:60px;border-radius:6px;" />', obj.image.url
            )
        return "—"


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    inlines = [ProductImageInline]
    list_display = (
        "name", "category", "price_fmt", "stock_quantity",
        "is_featured", "is_active", "badge",
    )
    list_editable = ("is_featured", "is_active")
    list_filter = ("category", "target", "badge", "is_active", "is_featured")
    search_fields = ("name", "brand", "sku")
    prepopulated_fields = {"slug": ("name",)}
    autocomplete_fields = ("category",)
    save_on_top = True

    fieldsets = (
        ("L'essentiel", {
            "fields": ("name", "category", "price", "compare_at_price",
                       "description", "is_active", "is_featured"),
        }),
        ("Détails produit", {
            "classes": ("collapse",),
            "fields": ("brand", "target", "badge", "sizes", "sku",
                       "stock_quantity", "slug"),
        }),
    )

    @admin.display(description="Prix", ordering="price")
    def price_fmt(self, obj):
        return f"{obj.price:,.0f} FCFA".replace(",", " ")
