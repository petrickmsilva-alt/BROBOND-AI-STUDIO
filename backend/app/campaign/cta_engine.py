"""V3.3 — CTA Engine: a campaign never says the same thing twice.

Every deliverable and every day of the timeline carries one call to action
(*"Vista o extraordinário."*, *"Legacy começa hoje."*). The rule of the
sprint is absolute: **nunca repetir CTA** — within a campaign, no CTA is
emitted twice.

The engine answers with a *deck*: the full template bank, formatted with
the campaign's product name and shuffled deterministically from a per-
campaign seed. Drawing from the deck's cursor can therefore never repeat,
by construction — and duplication mints a fresh seed, so a copied campaign
gets its own assignments. Framework-free: ``random.Random`` on an integer
seed, nothing else.

The bank is intentionally free of time-sensitive claims ("últimas peças",
"hoje é o último dia"): a deck is shuffled, so any CTA can land on any day,
and an honest campaign cannot have day 1 claiming scarcity.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from .brief_interpreter import CampaignValidationError

#: The brand fallback when the interpreter could not read a product name.
FALLBACK_PRODUCT = "a nova coleção"

#: The CTA template bank. Every template must be unique after formatting —
#: ``deck_for`` verifies it, so adding a duplicate here fails loudly in
#: tests instead of quietly repeating a CTA mid-campaign.
CTA_TEMPLATES: tuple[str, ...] = (
    "Vista o extraordinário.",
    "{name} começa hoje.",
    "O legado se veste: {name}.",
    "Sua vez de vestir {name}.",
    "Não siga. Vista {name}.",
    "{name} chegou — o resto é eco.",
    "Entre primeiro. Vista {name}.",
    "O novo padrão tem nome: {name}.",
    "{name}: presença que não pede licença.",
    "Garanta o seu {name}.",
    "{name} é agora.",
    "Quem chega primeiro veste {name}.",
    "{name} à altura da sua história.",
    "De {name} para quem define o próprio jogo.",
    "Experiência {name}, reservada a poucos.",
    "{name} não pede permissão.",
    "Feito para durar. Assinado {name}.",
    "{name} — o resto é imitação.",
    "Seu próximo capítulo se chama {name}.",
    "{name} para quem não espera a vez.",
    "Assine o legado: {name}.",
    "{name} já está na rua.",
    "Detalhe por detalhe, {name}.",
    "{name} fala antes de você.",
    "Presença construída: {name}.",
    "{name}. O resto é ruído.",
    "Vista {name}. Assuma o lugar.",
    "{name}. Simples assim.",
)

#: A campaign draws one CTA per deliverable plus one per timeline day; the
#: bank must always be strictly larger than that plan.
MIN_BANK_SIZE = 20


class CTAExhaustedError(RuntimeError):
    """Raised when a campaign needs more CTAs than the bank can supply."""


def _format(template: str, product: str) -> str:
    """Fill the ``{name}`` slot; plain templates pass through untouched."""

    return template.format(name=product) if "{name}" in template else template


def clean_product(product: object) -> str:
    """The deck's product name, or the brand fallback when unread."""

    if product is None:
        return FALLBACK_PRODUCT
    if not isinstance(product, str):
        raise CampaignValidationError("product must be a string")
    cleaned = product.strip()
    return cleaned or FALLBACK_PRODUCT


@dataclass
class CTADeck:
    """An ordered, non-repeating CTA sequence for exactly one campaign."""

    product: str
    seed: int
    ctas: tuple[str, ...]
    _cursor: int = field(default=0, repr=False, compare=False)

    def __post_init__(self) -> None:
        folded = [cta.casefold() for cta in self.ctas]
        if len(set(folded)) != len(folded):
            raise CampaignValidationError("CTA deck must not repeat a call to action")

    @property
    def remaining(self) -> int:
        """How many CTAs the campaign can still draw."""

        return len(self.ctas) - self._cursor

    def draw(self) -> str:
        """The next CTA. Past the end of the deck it refuses, never repeats."""

        if self._cursor >= len(self.ctas):
            raise CTAExhaustedError(
                f"CTA bank exhausted for {self.product!r}: {len(self.ctas)} unique CTAs were already drawn"
            )
        cta = self.ctas[self._cursor]
        self._cursor += 1
        return cta

    def draw_many(self, count: int) -> tuple[str, ...]:
        """Draw ``count`` CTAs, refusing (before mutating) when short."""

        if not isinstance(count, int) or isinstance(count, bool):
            raise CampaignValidationError("count must be an int")
        if count < 0:
            raise CampaignValidationError("count must not be negative")
        if count > self.remaining:
            raise CTAExhaustedError(
                f"CTA bank exhausted: {count} requested, {self.remaining} remaining"
            )
        drawn = tuple(self.ctas[self._cursor + offset] for offset in range(count))
        self._cursor += count
        return drawn


def deck_for(product: object, seed: int) -> CTADeck:
    """Build the deterministic, shuffled CTA deck for one campaign.

    The same ``(product, seed)`` always yields the same deck — a stored
    ``seed`` reproduces exactly the campaign's assignments — while two
    campaigns (or a duplicate with a fresh seed) never share an order.
    """

    if isinstance(seed, bool) or not isinstance(seed, int):
        raise CampaignValidationError("seed must be an int")
    if len(CTA_TEMPLATES) < MIN_BANK_SIZE:
        raise CampaignValidationError("CTA bank is below the minimum size")
    cleaned = clean_product(product)
    rng = random.Random(f"{seed}:{cleaned.casefold()}")
    ordered = list(CTA_TEMPLATES)
    rng.shuffle(ordered)
    return CTADeck(
        product=cleaned,
        seed=seed,
        ctas=tuple(_format(template, cleaned) for template in ordered),
    )
