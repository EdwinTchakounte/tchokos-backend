from django.urls import path, include
from rest_framework.routers import DefaultRouter

from . import views
from . import courier_views
from . import sendo_views
from . import vendor_views as admin_views  # CMS produits = espace admin
from . import admin_orders_views  # back-office commandes / paiements / ventes
from . import admin_delivery_views  # back-office livraisons / zones / décaissements

router = DefaultRouter()
router.register("categories", views.CategoryViewSet, basename="category")
router.register("products", views.ProductViewSet, basename="product")

urlpatterns = [
    path("", include(router.urls)),
    # Authentification (email+mdp / JWT / OTP)
    path("auth/", include("accounts.urls")),
    path("site-config/", views.site_config, name="site-config"),
    path("delivery-zones/", views.delivery_zones, name="delivery-zones"),
    path("orders/", views.create_order, name="create-order"),
    path("orders/mine/", views.my_orders, name="my-orders"),
    # Paiements Tara (init dans create_order, webhook + polling + réconciliation)
    path("payments/", include("payments.urls")),
    path("contact/", views.contact, name="contact"),
    path("chat/", views.chat, name="chat"),
    # Webhook entrant de Sendo (suivi de livraison)
    path("integrations/sendo/webhook/", sendo_views.sendo_webhook, name="sendo-webhook"),
    # Espace livreur — auth via /api/auth/ (email+mdp ou OTP) + inscription
    path("courier/zones/", courier_views.courier_zones, name="courier-zones"),
    path("courier/register/", courier_views.courier_register, name="courier-register"),
    path("courier/me/", courier_views.courier_me, name="courier-me"),
    path("courier/availability/", courier_views.courier_set_availability, name="courier-availability"),
    path("courier/deliveries/", courier_views.courier_deliveries, name="courier-deliveries"),
    path("courier/deliveries/<int:pk>/accept/", courier_views.courier_accept, name="courier-accept"),
    path("courier/deliveries/<int:pk>/complete/", courier_views.courier_complete, name="courier-complete"),
    # CMS produits — espace ADMIN (auth email+mdp, is_staff). Mobile + web.
    path("admin/dashboard/", admin_views.admin_dashboard, name="admin-dashboard"),
    path("admin/products/", admin_views.admin_create_product, name="admin-create-product"),
    path("admin/products/<int:pk>/", admin_views.admin_product_detail, name="admin-product-detail"),
    path("admin/products/<int:pk>/images/", admin_views.admin_product_images, name="admin-product-images"),
    path("admin/products/<int:pk>/images/<int:img_pk>/", admin_views.admin_product_image_detail, name="admin-product-image-detail"),
    # Back-office commandes / paiements / ventes
    path("admin/orders/", admin_orders_views.admin_orders, name="admin-orders"),
    path("admin/orders/<int:pk>/", admin_orders_views.admin_order_detail, name="admin-order-detail"),
    path("admin/orders/<int:pk>/contact/", admin_orders_views.admin_order_contact, name="admin-order-contact"),
    path("admin/payments/", admin_orders_views.admin_payments, name="admin-payments"),
    path("admin/sales-stats/", admin_orders_views.admin_sales_stats, name="admin-sales-stats"),
    path("admin/overview/", admin_orders_views.admin_overview, name="admin-overview"),
    # Back-office livraisons / zones / décaissements
    path("admin/deliveries/", admin_delivery_views.admin_deliveries, name="admin-deliveries"),
    path("admin/deliveries/<int:pk>/assign/", admin_delivery_views.admin_delivery_assign, name="admin-delivery-assign"),
    path("admin/couriers/", admin_delivery_views.admin_couriers, name="admin-couriers"),
    path("admin/couriers/<int:pk>/", admin_delivery_views.admin_courier_detail, name="admin-courier-detail"),
    path("admin/delivery-zones/", admin_delivery_views.admin_delivery_zones, name="admin-delivery-zones"),
    path("admin/delivery-zones/<int:pk>/", admin_delivery_views.admin_delivery_zone_detail, name="admin-delivery-zone-detail"),
    path("admin/settlements/", admin_delivery_views.admin_settlements, name="admin-settlements"),
    path("admin/settlements/<int:pk>/settle/", admin_delivery_views.admin_settlement_settle, name="admin-settlement-settle"),
]
