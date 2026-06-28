from django.urls import path, include
from rest_framework.routers import DefaultRouter

from . import views
from . import courier_views
from . import vendor_views

router = DefaultRouter()
router.register("categories", views.CategoryViewSet, basename="category")
router.register("products", views.ProductViewSet, basename="product")

urlpatterns = [
    path("", include(router.urls)),
    path("site-config/", views.site_config, name="site-config"),
    path("delivery-zones/", views.delivery_zones, name="delivery-zones"),
    path("orders/", views.create_order, name="create-order"),
    path("contact/", views.contact, name="contact"),
    # Espace livreur
    path("courier/login/", courier_views.courier_login, name="courier-login"),
    path("courier/deliveries/", courier_views.courier_deliveries, name="courier-deliveries"),
    path("courier/deliveries/<int:pk>/accept/", courier_views.courier_accept, name="courier-accept"),
    path("courier/deliveries/<int:pk>/complete/", courier_views.courier_complete, name="courier-complete"),
    # Espace vendeur
    path("vendor/login/", vendor_views.vendor_login, name="vendor-login"),
    path("vendor/dashboard/", vendor_views.vendor_dashboard, name="vendor-dashboard"),
    path("vendor/products/", vendor_views.vendor_create_product, name="vendor-create-product"),
    path("vendor/products/<int:pk>/", vendor_views.vendor_update_product, name="vendor-update-product"),
]
