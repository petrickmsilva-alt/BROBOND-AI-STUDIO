"""V3.3 — Brief Interpreter: one sentence in, a structured brief out.

The user writes a single line — *"Quero lançar a coleção Legacy"* — and the
interpreter extracts the six fields the Campaign Builder needs: **produto**,
**público**, **plataforma**, **duração**, **objetivo** and **CTA**. The CTA
is not parsed from the text; it is drawn from the ``cta_engine`` deck by the
campaign service, so it never repeats.

Design rules, inherited from the repository's discipline:

* deterministic — the same text always yields the same brief (no LLM, no
  network, no randomness);
* honest — every field the interpreter had to *default* instead of *read*
  is listed in ``missing``, so the UI can say which fields were inferred;
* framework-free — standard library only, like the rest of the decision
  modules. Persistence lives in ``campaign_repository.py``.

Portuguese first (the product's language), with the usual English marketing
vocabulary accepted. Matching is accent- and case-insensitive.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field


class CampaignValidationError(ValueError):
    """Raised when campaign input violates the domain vocabulary.

    The package kernel (same pattern as ``continuity/identity_lock.py``):
    routes map it to 422, and every campaign module imports it from here so
    it exists exactly once.
    """


# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------

#: Objective keywords, in priority order. The first objective whose keyword
#: appears in the text wins — "lançar" beats "vender" when both appear,
#: because a launch that sells is still a launch.
OBJECTIVES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("launch", ("lançar", "lançamento", "lancar", "launch", "estrear", "estreia", "debut")),
    ("sales", ("vender", "vendas", "conversão", "conversao", "sell", "sales", "checkout")),
    ("awareness", ("divulgar", "conhecimento", "awareness", "alcance", "viral")),
    ("engagement", ("engajar", "engajamento", "engagement", "comunidade", "seguidores")),
)

#: Platform keywords. The platform drives which deliverables lead the
#: timeline; the default is Instagram because the Reel 9:16 is the product's
#: flagship deliverable.
PLATFORMS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("instagram", ("instagram", "reels", "reel", "feed", "story", "stories")),
    ("tiktok", ("tiktok",)),
    ("youtube", ("youtube", "shorts", "canal")),
)

#: Audience keyword groups, in priority order (more specific first).
AUDIENCES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("público premium", ("alto padrão", "alto padrao", "premium", "luxo", "luxury", "classe a", "luxuos")),
    ("clientes VIP", ("vip", "clientes fiéis", "clientes fieis", "top clients")),
    ("executivos", ("executivo", "executivos", "empresário", "empresarios", "leaders")),
    ("público masculino", ("masculino", "homens", "men", "masculina")),
    ("público feminino", ("feminino", "mulheres", "women", "feminina")),
    ("público jovem", ("jovem", "jovens", "gen z", "young", "juventude")),
)

#: Product markers: the noun that introduces the product name
#: ("coleção Legacy", "tênis Apex 2"). Order matters only for readability.
PRODUCT_MARKERS: tuple[str, ...] = (
    "coleção cápsula",
    "colecao capsula",
    "coleção",
    "colecao",
    "linha",
    "drop",
    "série",
    "serie",
    "tênis",
    "tenis",
    "camisa",
    "calça",
    "calca",
    "jaqueta",
    "relógio",
    "relogio",
    "bolsa",
    "perfume",
    "óculos",
    "oculos",
    "produto",
    "collection",
    "sneaker",
)

#: Words that end a captured product name.
_STOP_WORDS = (
    "para",
    "com",
    "no",
    "na",
    "em",
    "que",
    "hoje",
    "amanhã",
    "amanha",
    "semana",
    "mês",
    "mes",
    "dia",
    "de",
    "e",
    "no brasil",
)

DEFAULT_AUDIENCE = "público premium"
DEFAULT_PLATFORM = "instagram"
DEFAULT_OBJECTIVE = "launch"
DEFAULT_DURATION_SECONDS = 15
DEFAULT_PRODUCT = "Nova coleção"

#: Deliverable videos live between 5 and 90 seconds.
MIN_DURATION_SECONDS = 5
MAX_DURATION_SECONDS = 90

#: Display forms for the product-type markers, keyed by their folded form,
#: so "Coleção" and "colecao" both read as "coleção" in the campaign.
PRODUCT_TYPE_DISPLAY: dict[str, str] = {
    "colecao capsula": "coleção cápsula",
    "colecao": "coleção",
    "serie": "série",
    "tenis": "tênis",
    "calca": "calça",
    "relogio": "relógio",
    "oculos": "óculos",
}

_MARKER_PATTERN = re.compile(
    r"(" + "|".join(sorted((re.escape(marker) for marker in PRODUCT_MARKERS), key=len, reverse=True)) + r")"
    r"\s+((?:de\s+)?)([a-z0-9][\w\-\']*(?:\s+[\w\-\']+)*)",
    re.IGNORECASE,
)
_QUOTED_PATTERN = re.compile(r"[\"'“”‘’]([\w][\w\-\' ]{0,60})[\"'“”‘’]")
_SECONDS_PATTERN = re.compile(r"(\d{1,3})\s*(?:s\b|seg\b|segundos?\b|seconds?\b)", re.IGNORECASE)
_MINUTES_PATTERN = re.compile(r"(\d{1,2})\s*(?:min\b|minutos?\b|minutes?\b)", re.IGNORECASE)
_FOR_PATTERN = re.compile(r"\bpara\s+((?:o|a|os|as)?\s?[a-zá-úà-ùâ-ûã-õç][\w\s\-]{2,60})", re.IGNORECASE)


def _fold(value: str) -> str:
    """Lowercase and strip accents, so matching survives 'coleção'/'colecao'."""

    decomposed = unicodedata.normalize("NFD", value)
    return "".join(char for char in decomposed if unicodedata.category(char) != "Mn").casefold()


# ---------------------------------------------------------------------------
# The brief
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class InterpretedBrief:
    """One briefing, read. Defaults are flagged in ``missing``, not hidden."""

    raw_text: str
    product: str = DEFAULT_PRODUCT
    product_type: str = ""
    audience: str = DEFAULT_AUDIENCE
    platform: str = DEFAULT_PLATFORM
    objective: str = DEFAULT_OBJECTIVE
    duration_seconds: int = DEFAULT_DURATION_SECONDS
    #: Filled by the CTA engine at creation time, never parsed from text.
    cta: str = ""
    missing: tuple[str, ...] = field(default=())
    matched: tuple[str, ...] = field(default=())

    @property
    def display_name(self) -> str:
        """The campaign's human name: product type + product when known."""

        if self.product_type and self.product:
            return f"{self.product_type} {self.product}".strip()
        return self.product or DEFAULT_PRODUCT

    def to_dict(self) -> dict[str, object]:
        return {
            "raw_text": self.raw_text,
            "product": self.product,
            "product_type": self.product_type,
            "audience": self.audience,
            "platform": self.platform,
            "objective": self.objective,
            "duration_seconds": self.duration_seconds,
            "cta": self.cta,
            "missing": list(self.missing),
            "matched": list(self.matched),
            "name": self.display_name,
        }


# ---------------------------------------------------------------------------
# Field extraction
# ---------------------------------------------------------------------------


def _first_keyword(text: str, table: tuple[tuple[str, tuple[str, ...]], ...]) -> tuple[str, str] | None:
    """Return (canonical value, matched keyword) for the earliest keyword hit.

    Both sides are accent-folded, so "padrão" in the text matches the
    "padrao" keyword — folding is length-preserving for precomposed
    characters, so positions stay comparable.
    """

    folded_text = _fold(text)
    best: tuple[int, str, str] | None = None
    for canonical, keywords in table:
        for keyword in keywords:
            position = folded_text.find(_fold(keyword))
            if position >= 0 and (best is None or position < best[0]):
                best = (position, canonical, keyword)
    if best is None:
        return None
    return best[1], best[2]


def _extract_product(text: str) -> tuple[str, str] | None:
    """Return (product name, product type) from markers or quotes.

    Runs on the original text (patterns are case-insensitive) so the
    product keeps the author's casing — "Legacy", not "legacy".
    """

    match = _MARKER_PATTERN.search(text)
    if match:
        folded_type = _fold(match.group(1))
        product_type = PRODUCT_TYPE_DISPLAY.get(folded_type, folded_type)
        candidate = _clean_product_name(match.group(3))
        if candidate:
            return candidate, product_type
    quoted = _QUOTED_PATTERN.search(text)
    if quoted:
        candidate = _clean_product_name(quoted.group(1))
        if candidate:
            return candidate, ""
    return None


def _clean_product_name(candidate: str) -> str:
    """Trim stop words and stray connectors off a captured product name."""

    words: list[str] = []
    for word in candidate.strip().split():
        folded = _fold(word)
        if folded in _STOP_WORDS:
            break
        words.append(word)
    name = " ".join(words).strip(" -',")
    return name if len(name) >= 2 else ""


def _extract_duration(text: str) -> int | None:
    """Duration in seconds from "15s", "30 segundos" or "1 minuto"."""

    minutes = _MINUTES_PATTERN.search(text)
    if minutes:
        value = int(minutes.group(1)) * 60
        if MIN_DURATION_SECONDS <= value <= MAX_DURATION_SECONDS:
            return value
    seconds = _SECONDS_PATTERN.search(text)
    if seconds:
        value = int(seconds.group(1))
        if MIN_DURATION_SECONDS <= value <= MAX_DURATION_SECONDS:
            return value
    return None


def _extract_audience(text: str) -> tuple[str, str] | None:
    """Keyword groups first, then a raw "para ..." capture."""

    keyword_hit = _first_keyword(text, AUDIENCES)
    if keyword_hit:
        return keyword_hit
    match = _FOR_PATTERN.search(text)
    if match:
        captured = match.group(1).strip()
        # Drop the leading article ("para o público masculino" reads better
        # without the dangling "o").
        for article in ("o ", "a ", "os ", "as "):
            if captured.casefold().startswith(article):
                captured = captured[len(article):]
                break
        captured = captured.strip()
        if 2 <= len(captured) <= 80:
            return captured, ""
    return None


def interpret(raw_text: object) -> InterpretedBrief:
    """Read one briefing line and return the structured ``InterpretedBrief``.

    Raises ``CampaignValidationError`` for blank or non-string input —
    routes map that to 422. Everything else is answered: fields the text
    does not carry get the documented default and a ``missing`` entry.
    """

    if not isinstance(raw_text, str):
        raise CampaignValidationError("briefing must be a string")
    cleaned = raw_text.strip()
    if not cleaned:
        raise CampaignValidationError("briefing must not be blank")
    if len(cleaned) > 2000:
        raise CampaignValidationError("briefing must be at most 2000 characters")

    text = _fold(cleaned)
    missing: list[str] = []
    matched: list[str] = []

    product_hit = _extract_product(cleaned)
    if product_hit:
        product, product_type = product_hit
        matched.append("produto")
    else:
        product, product_type = DEFAULT_PRODUCT, ""
        missing.append("produto")

    audience_hit = _extract_audience(cleaned)
    if audience_hit:
        audience, _ = audience_hit
        matched.append("público")
    else:
        audience = DEFAULT_AUDIENCE
        missing.append("público")

    platform_hit = _first_keyword(text, PLATFORMS)
    if platform_hit:
        platform, _ = platform_hit
        matched.append("plataforma")
    else:
        platform = DEFAULT_PLATFORM
        missing.append("plataforma")

    duration = _extract_duration(text)
    if duration is not None:
        matched.append("duração")
    else:
        duration = DEFAULT_DURATION_SECONDS
        missing.append("duração")

    objective_hit = _first_keyword(text, OBJECTIVES)
    if objective_hit:
        objective, _ = objective_hit
        matched.append("objetivo")
    else:
        objective = DEFAULT_OBJECTIVE
        missing.append("objetivo")

    return InterpretedBrief(
        raw_text=cleaned,
        product=product,
        product_type=product_type,
        audience=audience,
        platform=platform,
        objective=objective,
        duration_seconds=duration,
        missing=tuple(missing),
        matched=tuple(matched),
    )
