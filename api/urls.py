from django.urls import path, include
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("categories", views.CategoryViewSet, basename="category")
router.register("products", views.ProductViewSet, basename="product")

urlpatterns = [
    path("", include(router.urls)),
    path("site-config/", views.site_config, name="site-config"),
    path("delivery-zones/", views.delivery_zones, name="delivery-zones"),
    path("orders/", views.create_order, name="create-order"),
    path("contact/", views.contact, name="contact"),
]
