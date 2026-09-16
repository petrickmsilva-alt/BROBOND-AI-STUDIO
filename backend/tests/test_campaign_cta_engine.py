"""V3.3 — CTA Engine: a campaign never says the same thing twice.

The sprint rule is absolute — *nunca repetir CTA*. These tests pin it from
three sides: drawing the whole deck never repeats, the same seed always
rebuilds the same deck (stored seeds reproduce assignments), and drawing
past the end refuses instead of repeating. The brand voice examples from
the sprint ("Vista o extraordinário.", "Legacy começa hoje.") must exist
verbatim.
"""
from __future__ import annotations

import pytest

from app.campaign.brief_interpreter import CampaignValidationError
from app.campaign.cta_engine import (
    CTA_TEMPLATES,
    FALLBACK_PRODUCT,
    MIN_BANK_SIZE,
    CTADeck,
    CTAExhaustedError,
    clean_product,
    deck_for,
)
from app.campaign.timeline_builder import DAY_PLAN, DELIVERABLES

#: What one campaign draws: primary + one per deliverable + one per day.
CAMPAIGN_DRAWS = 1 + len(DELIVERABLES) + len(DAY_PLAN)


# ---------------------------------------------------------------------------
# The bank
# ---------------------------------------------------------------------------


def test_the_sprint_examples_exist_verbatim() -> None:
    assert "Vista o extraordinário." in CTA_TEMPLATES
    assert "{name} começa hoje." in CTA_TEMPLATES


def test_the_bank_is_unique_and_large_enough() -> None:
    assert len(CTA_TEMPLATES) >= MIN_BANK_SIZE
    folded = [template.casefold() for template in CTA_TEMPLATES]
    assert len(set(folded)) == len(folded), "the bank itself must not repeat a CTA"


def test_the_bank_never_claims_time_sensitive_scarcity() -> None:
    """A deck is shuffled: any CTA can land on day 1, so none may lie."""

    forbidden = ("última", "últimas", "últimos", "acaba hoje", "só hoje", "expira")
    for template in CTA_TEMPLATES:
        for word in forbidden:
            assert word not in template.casefold(), template


def test_the_formatted_deck_is_unique_for_a_product() -> None:
    deck = deck_for("Legacy", 7)
    folded = [cta.casefold() for cta in deck.ctas]
    assert len(set(folded)) == len(folded)


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_the_same_product_and_seed_rebuild_the_same_deck() -> None:
    assert deck_for("Legacy", 42).ctas == deck_for("Legacy", 42).ctas


def test_a_different_seed_shuffles_differently() -> None:
    assert deck_for("Legacy", 42).ctas != deck_for("Legacy", 99).ctas


def test_the_seed_is_an_int_and_bools_are_refused() -> None:
    with pytest.raises(CampaignValidationError):
        deck_for("Legacy", True)  # type: ignore[arg-type]
    with pytest.raises(CampaignValidationError):
        deck_for("Legacy", "42")  # type: ignore[arg-type]


def test_a_non_string_product_is_refused() -> None:
    with pytest.raises(CampaignValidationError):
        deck_for(42, 1)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Drawing — the never-repeat guarantee
# ---------------------------------------------------------------------------


def test_drawing_a_full_campaign_never_repeats() -> None:
    deck = deck_for("Legacy", 11)
    drawn = [deck.draw() for _ in range(CAMPAIGN_DRAWS)]
    assert len(drawn) == CAMPAIGN_DRAWS
    assert len({cta.casefold() for cta in drawn}) == CAMPAIGN_DRAWS
    assert deck.remaining == len(CTA_TEMPLATES) - CAMPAIGN_DRAWS


def test_drawing_the_whole_deck_never_repeats() -> None:
    deck = deck_for("Legacy", 3)
    drawn = [deck.draw() for _ in range(len(CTA_TEMPLATES))]
    assert len({cta.casefold() for cta in drawn}) == len(CTA_TEMPLATES)
    with pytest.raises(CTAExhaustedError):
        deck.draw()


def test_draw_many_refuses_before_mutating() -> None:
    deck = deck_for("Legacy", 5)
    with pytest.raises(CTAExhaustedError):
        deck.draw_many(len(CTA_TEMPLATES) + 1)
    # The failed draw consumed nothing: a full campaign still fits.
    assert deck.draw_many(CAMPAIGN_DRAWS) == deck.ctas[:CAMPAIGN_DRAWS]


@pytest.mark.parametrize("bad", [-1, "3", True, None, 1.5])
def test_draw_many_validates_the_count(bad) -> None:
    deck = deck_for("Legacy", 5)
    with pytest.raises(CampaignValidationError):
        deck.draw_many(bad)


def test_draw_many_zero_draws_nothing() -> None:
    deck = deck_for("Legacy", 5)
    assert deck.draw_many(0) == ()
    assert deck.remaining == len(CTA_TEMPLATES)


# ---------------------------------------------------------------------------
# The product name
# ---------------------------------------------------------------------------


def test_the_cta_carries_the_product_name() -> None:
    deck = deck_for("Legacy", 8)
    assert any("Legacy" in cta for cta in deck.ctas)
    assert all(cta.endswith((".", "!", "?")) for cta in deck.ctas), "a CTA is a sentence"


def test_a_blank_product_falls_back_to_the_brand_voice() -> None:
    assert clean_product("") == FALLBACK_PRODUCT
    assert clean_product(None) == FALLBACK_PRODUCT
    deck = deck_for("", 4)
    assert deck.product == FALLBACK_PRODUCT
    assert FALLBACK_PRODUCT in " ".join(deck.ctas)


def test_clean_product_strips_and_rejects_non_strings() -> None:
    assert clean_product("  Legacy  ") == "Legacy"
    with pytest.raises(CampaignValidationError):
        clean_product(7)


# ---------------------------------------------------------------------------
# Deck integrity
# ---------------------------------------------------------------------------


def test_a_deck_cannot_be_built_with_repeats() -> None:
    with pytest.raises(CampaignValidationError):
        CTADeck(product="X", seed=1, ctas=("Vista o extraordinário.", "vista O EXTRAORDINÁRIO."))


def test_deck_exposes_its_seed_and_product() -> None:
    deck = deck_for("Legacy", 13)
    assert deck.seed == 13
    assert deck.product == "Legacy"


def test_a_shrunk_bank_is_refused_at_deck_time(monkeypatch) -> None:
    from app.campaign import cta_engine

    monkeypatch.setattr(cta_engine, "CTA_TEMPLATES", ("só uma.",))
    with pytest.raises(CampaignValidationError):
        cta_engine.deck_for("Legacy", 1)
