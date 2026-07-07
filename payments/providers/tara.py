"""Implémentation du provider Tara Money (Mobile Money MTN / Orange Cameroun).

Adapté de la brique durcie Gathé Finance. Décisions de mapping :
  - On utilise notre `Payment.idempotency_key` (UUID) comme `productId` Tara :
    Tara dédoublonne ses relances dessus, et on retrouve le Payment local
    depuis le webhook sans exposer nos IDs de base.
  - On envoie `webHookUrl` par requête (Tara autorise l'override par appel) :
    chaque environnement (dev / prod) reçoit son propre callback.
  - Sans crédentials → **mode mock** : aucun appel HTTP, référence factice.
    Pratique en dev ; jamais en prod (poser TARA_API_KEY + TARA_MERCHANT_ID).

Endpoints Tara servis sur ``dklo.co`` (doc développeur taramoney.com).
"""
from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

import requests
from django.conf import settings

from .base import (
    InitPayinResult,
    PaymentProviderBase,
    PayoutResult,
    ProviderError,
    WebhookEvent,
)

if TYPE_CHECKING:
    from payments.models import Payment


logger = logging.getLogger(__name__)


class TaraProvider(PaymentProviderBase):
    code = "tara"
    BASE_URL = "https://www.dklo.co"
    TIMEOUT_SECONDS = 15

    def __init__(self) -> None:
        # Tchokos nomme le marchand TARA_MERCHANT_ID ; on accepte aussi
        # TARA_BUSINESS_ID (nom d'origine de la brique) par compatibilité.
        self.api_key = getattr(settings, "TARA_API_KEY", "") or ""
        self.business_id = (
            getattr(settings, "TARA_MERCHANT_ID", "")
            or getattr(settings, "TARA_BUSINESS_ID", "")
            or ""
        )
        self.webhook_secret = getattr(settings, "TARA_WEBHOOK_SECRET", "") or ""

    @property
    def _mock_mode(self) -> bool:
        """Sans crédentials, on saute l'appel HTTP et on renvoie une référence
        factice. Se marie avec l'endpoint dev ``/api/payments/dev/<id>/confirm/``
        qui simule le webhook localement.
        """
        return not (self.api_key and self.business_id)

    # -- Payin (encaissement entrant) ---------------------------------------

    def init_payin(self, payment: "Payment", *, phone: str, network: str) -> InitPayinResult:
        """Initie un paiement Tara — STK Push direct sur le téléphone.

        Réponse Cameroun (MTN/Orange) : ``{status, message, vendor}`` — pas de
        transactionId ni de page hébergée : Tara pousse un popup USSD sur le
        téléphone du client, qui valide avec son PIN MoMo. Le webhook suit.
        """
        if self._mock_mode:
            logger.warning(
                "TaraProvider en mode MOCK (pas de clé) — pas d'appel HTTP, référence factice."
            )
            return InitPayinResult(
                provider_reference=f"MOCK-{payment.idempotency_key}",
                payment_url=None,
                raw={"mock": True, "reason": "TARA_API_KEY/TARA_MERCHANT_ID non configurés"},
            )
        product_name = f"Commande Tchokos {payment.order.reference}"
        payload: dict = {
            "apiKey": self.api_key,
            "businessId": self.business_id,
            "productId": str(payment.idempotency_key),
            "productName": product_name,
            "productPrice": int(payment.montant),  # int XAF, pas string
            "phoneNumber": self._normalize_phone(phone),  # 2376xxxxxxx
            "webHookUrl": self._webhook_url(),
            # network vide : Tara détecte le réseau via le préfixe du numéro.
            "network": "",
            "productDescription": product_name,
            "returnUrl": self._return_url(),
        }
        data = self._post("/api/tara/mobilepay", payload)
        logger.info(
            "[TARA] init_payin OK — phone=%s price=%s productId=%s → %s",
            payload.get("phoneNumber"),
            payload.get("productPrice"),
            payload.get("productId"),
            data,
        )
        return InitPayinResult(
            provider_reference=str(payment.idempotency_key),
            payment_url=data.get("authUrl"),  # Wave uniquement, sinon None
            raw={**data, "_hint_phone": phone, "_hint_network": network},
        )

    # -- Poll de statut (cron de réconciliation) ----------------------------

    def check_status(self, payment: "Payment") -> str:
        if self._mock_mode:
            # Le mode mock n'auto-confirme jamais — la confirmation passe par
            # l'endpoint dev / la commande manuelle.
            return "en_attente"
        payload = {
            "apiKey": self.api_key,
            "businessId": self.business_id,
            "productId": str(payment.idempotency_key),
        }
        data = self._post("/api/tara/transactions/status", payload)
        raw_status = (data.get("status") or "").upper()
        return _STATUS_MAP.get(raw_status, "en_attente")

    # -- Payout (sortant — non utilisé côté vitrine) ------------------------

    def init_payout(self, payment: "Payment", *, recipient_phone: str, network: str) -> PayoutResult:
        if self._mock_mode:
            logger.warning("TaraProvider payout en mode MOCK — référence factice.")
            return PayoutResult(
                provider_reference=f"MOCK-PAYOUT-{payment.idempotency_key}",
                raw={"mock": True},
            )
        payload = {
            "apiKey": self.api_key,
            "businessId": self.business_id,
            "receiverName": payment.order.customer_name if payment.order_id else "",
            "paymentMethod": "MOBILE_MONEY",
            "receiverPhoneNumber": self._normalize_phone(recipient_phone),
            "receiverId": self._normalize_phone(recipient_phone),
            "amount": str(int(payment.montant)),
            "network": (network or "").upper(),
        }
        # NB : la doc Tara orthographie littéralement « paypout » (typo côté
        # Tara, mais c'est le path réel attendu par leur API).
        data = self._post("/api/tara/paypout/create", payload)
        return PayoutResult(provider_reference=str(data.get("payoutId") or ""), raw=data)

    # -- Authentification + normalisation du webhook ------------------------

    def verify_webhook(self, body: bytes, signature_header: str) -> WebhookEvent:
        """Vérifie un webhook Tara.

        Tara NE SIGNE PAS ses webhooks (pas de HMAC). La sécurité repose sur :
        HTTPS + URL de webhook secrète + vérification du `businessId`. On refuse
        tout webhook dont le `businessId` ne correspond pas au nôtre.

        Mapping : productId/collectionId → clé de matching, paymentId →
        reference, status → SUCCESS/FAILURE.
        """
        try:
            payload = self._parse_json(body)
        except ValueError as exc:
            raise ProviderError(f"Webhook body malformé : {exc}", retryable=False) from exc

        if (
            self.business_id
            and payload.get("businessId")
            and payload["businessId"] != self.business_id
        ):
            raise ProviderError(
                f"businessId du webhook incohérent : {payload.get('businessId')!r}",
                retryable=False,
            )

        return WebhookEvent(
            payment_idempotency_key=str(
                payload.get("productId") or payload.get("collectionId") or "",
            ),
            status=_STATUS_MAP.get((payload.get("status") or "").upper(), "en_attente"),
            provider_reference=str(payload.get("paymentId") or ""),
            raw=payload,
        )

    # -- Internes -----------------------------------------------------------

    def _webhook_url(self) -> str:
        base = getattr(settings, "PUBLIC_BASE_URL", "").rstrip("/")
        return f"{base}/api/payments/webhook/tara/"

    def _return_url(self) -> str:
        base = getattr(settings, "FRONTEND_URL", "").rstrip("/")
        return f"{base}/" if base else ""

    def _post(self, path: str, payload: dict) -> dict:
        try:
            response = requests.post(
                f"{self.BASE_URL}{path}", json=payload, timeout=self.TIMEOUT_SECONDS
            )
        except requests.Timeout as exc:
            raise ProviderError(f"Tara timeout sur {path}", retryable=True) from exc
        except requests.RequestException as exc:
            raise ProviderError(f"Tara erreur réseau sur {path}: {exc}", retryable=True) from exc

        if response.status_code >= 500:
            raise ProviderError(
                f"Tara 5xx sur {path}: {response.status_code}",
                retryable=True,
                raw={"status_code": response.status_code, "body": response.text[:500]},
            )
        try:
            data = response.json()
        except ValueError as exc:
            raise ProviderError(
                f"Tara a renvoyé un non-JSON sur {path}: {response.text[:200]}",
                retryable=False,
            ) from exc

        if response.status_code >= 400:
            raise ProviderError(
                f"Tara erreur sur {path}: {data.get('message') or response.status_code}",
                retryable=False,
                raw=data,
            )
        if (data.get("status") or "").upper() in {"ERROR", "FAILED"}:
            raise ProviderError(
                f"Tara erreur métier : {data.get('message') or 'inconnue'}",
                retryable=False,
                raw=data,
            )
        return data

    @staticmethod
    def _parse_json(body: bytes) -> dict:
        return json.loads(body.decode("utf-8") or "{}")

    @staticmethod
    def _normalize_phone(raw: str) -> str:
        """Tara attend un numéro camerounais en ``2376xxxxxxx`` (sans +, sans espace)."""
        digits = "".join(c for c in (raw or "") if c.isdigit())
        if not digits:
            raise ProviderError("Numéro de téléphone vide", retryable=False)
        if digits.startswith("237"):
            return digits
        return f"237{digits.lstrip('0')}"


# Table de mapping Tara → Payment.statut interne.
_STATUS_MAP: dict[str, str] = {
    "SUCCESS": "valide",
    "VALIDATED": "valide",
    "COMPLETED": "valide",
    "PAID": "valide",
    "PENDING": "en_attente",
    "INITIATED": "en_attente",
    "FAILED": "rejete",
    "REJECTED": "rejete",
    "CANCELLED": "rejete",
    "ERROR": "rejete",
}
