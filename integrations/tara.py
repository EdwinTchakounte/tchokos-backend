"""Hook d'intégration Tara Money (https://taramoney.com).

Tara Money est un assistant de paiement conversationnel (Mobile Money via
WhatsApp / Telegram, MTN MoMo & Orange Money au Cameroun) qui propose des
« liens de paiement » marchands.

⚠️  Phase 1 : la vitrine encaisse via WhatsApp. Ce module pose seulement
l'ARCHITECTURE pour brancher Tara plus tard. ``create_payment_link`` est
volontairement un stub : il renvoie un lien factice si aucune credential
n'est configurée, et documente l'emplacement de l'appel API réel.

Pour activer : renseigner TARA_API_KEY / TARA_MERCHANT_ID dans .env, puis
implémenter l'appel HTTP réel d'après la doc Tara dans ``_call_tara_api``.
"""
import logging
from dataclasses import dataclass
from decimal import Decimal

from django.conf import settings

logger = logging.getLogger(__name__)


@dataclass
class PaymentLink:
    url: str
    reference: str
    provider: str = "tara"
    is_stub: bool = False


def is_configured() -> bool:
    return bool(getattr(settings, "TARA_API_KEY", "")) and bool(
        getattr(settings, "TARA_MERCHANT_ID", "")
    )


def create_payment_link(
    *, amount: Decimal, reference: str, description: str = "", customer_phone: str = ""
) -> PaymentLink:
    """Crée un lien de paiement Tara Money pour une commande.

    Renvoie un ``PaymentLink``. Tant que Tara n'est pas configuré, renvoie un
    lien stub (is_stub=True) pour ne pas bloquer le développement.
    """
    if not is_configured():
        logger.info(
            "[Tara] non configuré — lien stub généré (ref=%s, montant=%s)",
            reference, amount,
        )
        return PaymentLink(
            url=f"https://taramoney.com/pay/STUB-{reference}",
            reference=reference,
            is_stub=True,
        )
    return _call_tara_api(
        amount=amount,
        reference=reference,
        description=description,
        customer_phone=customer_phone,
    )


def _call_tara_api(*, amount, reference, description, customer_phone) -> PaymentLink:
    """Appel HTTP réel à l'API Tara Money.

    À implémenter d'après la documentation marchand de Tara une fois les
    credentials obtenues. Laisser le stub ci-dessus actif en attendant.
    """
    raise NotImplementedError(
        "Brancher l'appel API Tara Money ici (voir doc marchand taramoney.com)."
    )
