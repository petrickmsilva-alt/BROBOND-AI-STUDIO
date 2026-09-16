"""V3.3 — Brief Interpreter: one line in, six fields out.

Pins the sprint's example (*"Quero lançar a coleção Legacy"*), the accent-
and case-insensitive matching, the honest ``missing`` list for defaulted
fields and the validation errors the routes map to 422.
"""
from __future__ import annotations

import pytest

from app.campaign.brief_interpreter import (
    DEFAULT_AUDIENCE,
    DEFAULT_DURATION_SECONDS,
    DEFAULT_OBJECTIVE,
    DEFAULT_PLATFORM,
    DEFAULT_PRODUCT,
    CampaignValidationError,
    InterpretedBrief,
    interpret,
)


# ---------------------------------------------------------------------------
# The sprint example
# ---------------------------------------------------------------------------


def test_the_sprint_example_reads_product_type_and_objective() -> None:
    brief = interpret("Quero lançar a coleção Legacy")

    assert brief.product == "Legacy"
    assert brief.product_type == "coleção"
    assert brief.objective == "launch"
    assert brief.display_name == "coleção Legacy"
    # Everything the text did not carry is defaulted *and* flagged.
    assert set(brief.missing) == {"público", "plataforma", "duração"}
    assert brief.matched == ("produto", "objetivo")
    assert brief.audience == DEFAULT_AUDIENCE
    assert brief.platform == DEFAULT_PLATFORM
    assert brief.duration_seconds == DEFAULT_DURATION_SECONDS


def test_the_interpreter_preserves_the_author_casing() -> None:
    brief = interpret("Linha AURORA Pantheon para o público jovem no tiktok")
    assert brief.product == "AURORA Pantheon"
    assert brief.product_type == "linha"


def test_a_full_briefing_matches_all_six_fields_but_the_cta() -> None:
    brief = interpret(
        "Quero lançar a coleção Legacy para o público premium no instagram, "
        "vídeos de 15 segundos"
    )
    assert brief.product == "Legacy"
    assert brief.audience == "público premium"
    assert brief.platform == "instagram"
    assert brief.duration_seconds == 15
    assert brief.objective == "launch"
    assert brief.missing == ()
    # The CTA is never parsed from the text; the CTA engine draws it.
    assert brief.cta == ""


# ---------------------------------------------------------------------------
# Field extraction
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "objective"),
    [
        ("Quero lançar a coleção Legacy", "launch"),
        ("campanha de vendas da coleção Legacy", "sales"),
        ("Quero divulgar a nova linha no youtube", "awareness"),
        ("vídeo para engajar a comunidade", "engagement"),
        ("campaign to sell the new drop", "sales"),
    ],
)
def test_objectives_map_from_the_text(text: str, objective: str) -> None:
    assert interpret(text).objective == objective


def test_launch_wins_when_launch_and_sales_both_appear() -> None:
    # A launch that sells is still a launch — the earliest keyword wins.
    assert interpret("lançar para vender mais").objective == "launch"


@pytest.mark.parametrize(
    ("text", "platform"),
    [
        ("coleção Legacy no instagram", "instagram"),
        ("coleção Legacy em reels", "instagram"),
        ("coleção Legacy no tiktok", "tiktok"),
        ("coleção Legacy no youtube com shorts", "youtube"),
    ],
)
def test_platforms_map_from_the_text(text: str, platform: str) -> None:
    assert interpret(text).platform == platform


@pytest.mark.parametrize(
    ("text", "audience"),
    [
        ("coleção Legacy para o público alto padrão", "público premium"),
        ("coleção Legacy luxury edition", "público premium"),
        ("coleção Legacy para homens", "público masculino"),
        ("coleção Legacy para mulheres elegantes", "público feminino"),
        ("coleção Legacy para o público jovem", "público jovem"),
        ("coleção Legacy para executivos", "executivos"),
        ("coleção Legacy para clientes VIP", "clientes VIP"),
    ],
)
def test_audiences_map_from_the_text(text: str, audience: str) -> None:
    assert interpret(text).audience == audience


def test_a_raw_para_capture_is_the_audience_fallback() -> None:
    brief = interpret("coleção Legacy para arquitetos de São Paulo")
    assert brief.audience == "arquitetos de São Paulo"
    assert "público" in brief.matched


def test_duration_reads_seconds_and_minutes() -> None:
    assert interpret("coleção X com vídeos de 30s").duration_seconds == 30
    assert interpret("coleção X com vídeos de 30 segundos").duration_seconds == 30
    assert interpret("coleção X com vídeo de 1 minuto").duration_seconds == 60


def test_a_duration_beyond_the_deliverable_bounds_is_defaulted_and_flagged() -> None:
    # "2 min" = 120s exceeds the 90s deliverable ceiling: the interpreter
    # answers with the default and flags the field instead of guessing.
    brief = interpret("coleção X com vídeos de 2 min")
    assert brief.duration_seconds == DEFAULT_DURATION_SECONDS
    assert "duração" in brief.missing


def test_a_plausible_duration_is_required() -> None:
    # "200s" exceeds the deliverable bounds: default + flag.
    brief = interpret("coleção X com vídeos de 200 segundos")
    assert brief.duration_seconds == DEFAULT_DURATION_SECONDS
    assert "duração" in brief.missing


def test_a_quoted_product_reads_without_a_marker() -> None:
    brief = interpret('lançar "Solaris" no tiktok')
    assert brief.product == "Solaris"
    assert brief.product_type == ""
    assert brief.display_name == "Solaris"


def test_stop_words_end_the_captured_product_name() -> None:
    brief = interpret("lançar a coleção Legacy para o público premium hoje")
    assert brief.product == "Legacy"


def test_accent_and_case_do_not_change_the_read() -> None:
    plain = interpret("Quero lançar a colecao Legacy no instagram")
    accented = interpret("quero lançar a COLEÇÃO Legacy no Instagram")
    assert plain.product == accented.product == "Legacy"
    assert plain.platform == accented.platform == "instagram"
    assert plain.objective == accented.objective


def test_to_dict_carries_the_name() -> None:
    payload = interpret("Quero lançar a coleção Legacy").to_dict()
    assert payload["name"] == "coleção Legacy"
    assert payload["product"] == "Legacy"
    assert set(payload) == {
        "raw_text",
        "name",
        "product",
        "product_type",
        "audience",
        "platform",
        "objective",
        "duration_seconds",
        "cta",
        "missing",
        "matched",
    }


def test_the_interpreter_is_deterministic() -> None:
    text = "Quero lançar a coleção Legacy para o público jovem no tiktok, 20s"
    assert interpret(text).to_dict() == interpret(text).to_dict()


def test_an_empty_product_gets_the_honest_default() -> None:
    brief = interpret("quero vender muito")
    assert brief.product == DEFAULT_PRODUCT
    assert "produto" in brief.missing


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad", ["", "   ", "\n\t"])
def test_blank_briefings_are_refused(bad: str) -> None:
    with pytest.raises(CampaignValidationError):
        interpret(bad)


def test_non_string_briefings_are_refused() -> None:
    with pytest.raises(CampaignValidationError):
        interpret(None)
    with pytest.raises(CampaignValidationError):
        interpret(42)


def test_overlong_briefings_are_refused() -> None:
    with pytest.raises(CampaignValidationError):
        interpret("coleção " + "a" * 3000)


def test_the_brief_is_frozen_data() -> None:
    brief = interpret("coleção Legacy")
    with pytest.raises(Exception):
        brief.product = "other"  # type: ignore[misc]


def test_default_constants_are_the_documented_ones() -> None:
    assert (DEFAULT_AUDIENCE, DEFAULT_PLATFORM, DEFAULT_OBJECTIVE) == (
        "público premium",
        "instagram",
        "launch",
    )
    assert DEFAULT_DURATION_SECONDS == 15
    assert DEFAULT_PRODUCT == "Nova coleção"
    assert isinstance(InterpretedBrief(raw_text="x").missing, tuple)


def test_the_para_capture_drops_the_leading_article() -> None:
    brief = interpret("coleção Legacy para o time de marketing")
    assert brief.audience == "time de marketing"
