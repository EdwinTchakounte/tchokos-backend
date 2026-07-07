"""Registre des providers de paiement — passerelles enfichables.

Un `Payment` porte `provider_code` (ex. "tara") ; le reste du code demande
`get_provider(code)` et travaille contre l'interface `PaymentProviderBase`.
Ajouter une passerelle = un fichier ici + une ligne ci-dessous.
"""
from __future__ import annotations

from .base import (
    InitPayinResult,
    PaymentProviderBase,
    PayoutResult,
    ProviderError,
    WebhookEvent,
)
from .tara import TaraProvider


_PROVIDERS: dict[str, type[PaymentProviderBase]] = {
    TaraProvider.code: TaraProvider,
}


def get_provider(code: str) -> PaymentProviderBase:
    """Retourne une instance fraîche du provider demandé.

    Lève `ValueError` si le code est inconnu — volontairement un échec dur
    plutôt qu'un no-op silencieux.
    """
    try:
        provider_cls = _PROVIDERS[code]
    except KeyError as exc:
        raise ValueError(f"Provider de paiement inconnu : {code!r}") from exc
    return provider_cls()


__all__ = [
    "get_provider",
    "PaymentProviderBase",
    "InitPayinResult",
    "PayoutResult",
    "WebhookEvent",
    "ProviderError",
    "TaraProvider",
]
