"""Interface abstraite que tout provider de paiement doit implémenter.

Ce fichier reste vierge de toute logique métier — uniquement le contrat.
``payments.services`` n'importe que les symboles définis ici, jamais un module
provider concret.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from payments.models import Payment


class ProviderError(Exception):
    """Enveloppe toute erreur non récupérable venant d'une passerelle."""

    def __init__(self, message: str, *, retryable: bool = False, raw: dict | None = None):
        super().__init__(message)
        self.retryable = retryable
        self.raw = raw or {}


@dataclass
class InitPayinResult:
    """Retour de ``init_payin()`` — ce qu'on stocke sur le `Payment` local."""

    provider_reference: str
    payment_url: str | None = None
    raw: dict = field(default_factory=dict)


@dataclass
class PayoutResult:
    """Retour de ``init_payout()`` — transfert sortant (non utilisé en e-commerce)."""

    provider_reference: str
    raw: dict = field(default_factory=dict)


@dataclass
class WebhookEvent:
    """Payload webhook normalisé — chaque provider traduit sa forme native ici."""

    payment_idempotency_key: str
    status: str  # "valide" | "en_attente" | "rejete"
    provider_reference: str
    raw: dict = field(default_factory=dict)


class PaymentProviderBase(ABC):
    """Interface commune à toute passerelle Mobile Money / carte / virement."""

    #: Identifiant court stable, persisté sur `Payment.provider_code`.
    code: str = ""

    @abstractmethod
    def init_payin(self, payment: "Payment", *, phone: str, network: str) -> InitPayinResult:
        """Pousse une demande de paiement entrant (STK Push MoMo).

        DOIT être idempotent : passer deux fois le même `idempotency_key` ne
        doit pas créer deux transactions.
        """

    @abstractmethod
    def check_status(self, payment: "Payment") -> str:
        """Interroge la passerelle sur l'état courant d'un paiement en cours.

        Retourne : ``"valide"`` | ``"en_attente"`` | ``"rejete"``.
        Utilisé par le cron de réconciliation et les actions admin manuelles.
        """

    @abstractmethod
    def init_payout(self, payment: "Payment", *, recipient_phone: str, network: str) -> PayoutResult:
        """Envoie de l'argent VERS un bénéficiaire (non utilisé côté vitrine)."""

    @abstractmethod
    def verify_webhook(self, body: bytes, signature_header: str) -> WebhookEvent:
        """Authentifie le webhook et le traduit en `WebhookEvent`.

        DOIT lever `ProviderError` si la vérification échoue — ne jamais
        retourner un événement pour une requête non vérifiée.
        """
