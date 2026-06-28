from django.conf import settings
from django.urls import include, path
from django.contrib import admin

from wagtail.admin import urls as wagtailadmin_urls
from wagtail import urls as wagtail_urls
from wagtail.documents import urls as wagtaildocs_urls

from search import views as search_views
from .api import wagtail_api_router

# Back-office produits dédié (admin Django) — habillage Tchokos
admin.site.site_header = "Tchokos — Gestion"
admin.site.site_title = "Tchokos"
admin.site.index_title = "Produits, catégories & commandes"

urlpatterns = [
    # API REST (catalogue, commandes, contact, config) consommée par Next.js
    path("api/", include("api.urls")),
    # API Wagtail v2 (pages éditoriales : accueil, à propos)
    path("api/cms/", wagtail_api_router.urls),
    # Back-office produits / commandes (équipe Tchokos)
    path("gestion/", admin.site.urls),
    # CMS éditorial Wagtail (pages marketing, réglages marque)
    path("cms/", include(wagtailadmin_urls)),
    path("documents/", include(wagtaildocs_urls)),
    path("search/", search_views.search, name="search"),
]


if settings.DEBUG:
    from django.conf.urls.static import static
    from django.contrib.staticfiles.urls import staticfiles_urlpatterns

    urlpatterns += staticfiles_urlpatterns()
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

urlpatterns = urlpatterns + [
    path("", include(wagtail_urls)),
]
