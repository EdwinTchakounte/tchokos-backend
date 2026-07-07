from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from . import views

urlpatterns = [
    path("login/", views.LoginView.as_view(), name="auth-login"),
    path("register/", views.register, name="auth-register"),
    path("token/refresh/", TokenRefreshView.as_view(), name="auth-refresh"),
    path("logout/", views.logout, name="auth-logout"),
    path("me/", views.me, name="auth-me"),
    path("password/change/", views.change_password, name="auth-password-change"),
    path("password/reset/", views.password_reset_request, name="auth-password-reset"),
    path("password/reset/confirm/", views.password_reset_confirm, name="auth-password-reset-confirm"),
    path("otp/request/", views.otp_request, name="auth-otp-request"),
    path("otp/verify/", views.otp_verify, name="auth-otp-verify"),
]
