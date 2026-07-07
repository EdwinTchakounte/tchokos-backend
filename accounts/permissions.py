from rest_framework.permissions import BasePermission


class IsAdminRole(BasePermission):
    """Réservé à l'équipe Tchokos (admin / staff) — gère le catalogue."""
    message = "Accès réservé à l'administration."

    def has_permission(self, request, view):
        u = request.user
        return bool(u and u.is_authenticated and (u.is_staff or getattr(u, "role", "") == "admin"))


class IsCourier(BasePermission):
    """Réservé aux livreurs (compte avec profil courier)."""
    message = "Accès réservé aux livreurs."

    def has_permission(self, request, view):
        u = request.user
        return bool(u and u.is_authenticated and hasattr(u, "courier_profile"))
