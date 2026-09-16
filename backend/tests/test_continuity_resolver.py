"""V3.2 — the Continuity Resolver over a fake store.

``resolve(persona_id, campaign_id, episode)`` returns one ContinuityContext:
typed snapshots, cinematic phrases, stored fingerprints, missing locks,
drift and consistency. The GenerationSpec is never touched — these tests pin
the context shape and the resolution rules without any database.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

import pytest

from app.continuity import (
    LOCK_ORDER,
    ContinuityContext,
    ContinuityResolver,
    ContinuityValidationError,
    IdentityLock,
    LocationLock,
    VehicleLock,
    VoiceLock,
    WardrobeLock,
)
from app.continuity.continuity_resolver import _rebuild


@dataclass(frozen=True)
class FakeStoredLock:
    payload: Mapping[str, object] = field(default_factory=dict)
    fingerprint: str = ""


class FakeStore:
    """In-memory ContinuityStore keyed by (lock_type, persona, campaign, episode)."""

    def __init__(self) -> None:
        self._locks: dict[tuple[str, str, str, int | None], FakeStoredLock] = {}

    def put(
        self,
        lock_type: str,
        persona_id: str,
        campaign_id: str,
        episode: int | None,
        payload: dict,
        fingerprint: str,
    ) -> None:
        self._locks[(lock_type, persona_id, campaign_id, episode)] = FakeStoredLock(payload, fingerprint)

    def get_lock(self, lock_type, persona_id, campaign_id, episode):
        return self._locks.get((lock_type, persona_id, campaign_id, episode))


def _full_store(persona: str = "CHAR_PETRICK", campaign: str = "legacy", episode: int = 1) -> FakeStore:
    identity = IdentityLock.lock(persona, face="oval face", hair="tied back")
    wardrobe = WardrobeLock.lock(outfit="black blazer", watch="steel chronograph")
    location = LocationLock.lock(showroom="Flagship", city="São Paulo")
    vehicle = VehicleLock.lock(vehicle="RAM 1500", color="branco pérola")
    voice = VoiceLock.lock(voice_profile="petrick-low-warm", default_emotion="confident")
    store = FakeStore()
    store.put("identity", persona, campaign, episode, {**identity.to_dict(), "persona_id": persona}, identity.fingerprint)
    store.put("wardrobe", persona, campaign, episode, wardrobe.to_dict(), wardrobe.fingerprint)
    store.put("location", persona, campaign, episode, location.to_dict(), location.fingerprint)
    store.put("vehicle", persona, campaign, episode, vehicle.to_dict(), vehicle.fingerprint)
    store.put("voice", persona, campaign, episode, voice.to_dict(), voice.fingerprint)
    return store


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_lock_order_is_identity_first_voice_last() -> None:
    assert LOCK_ORDER == ("identity", "wardrobe", "location", "vehicle", "voice")


def test_resolve_returns_one_context_with_five_snapshots() -> None:
    context = ContinuityResolver(_full_store()).resolve("CHAR_PETRICK", "legacy", 1)
    assert (context.persona_id, context.campaign_id, context.episode) == ("CHAR_PETRICK", "legacy", 1)
    assert context.identity is not None and context.identity.face == "oval face"
    assert context.wardrobe is not None and context.wardrobe.outfit == "black blazer"
    assert context.location is not None and context.location.showroom == "Flagship"
    assert context.vehicle is not None and context.vehicle.vehicle == "RAM 1500"
    assert context.voice is not None and context.voice.voice_profile == "petrick-low-warm"
    assert context.missing == ()
    assert context.drift == ()
    assert context.consistent is True


def test_resolve_phrases_follow_the_fixed_lock_order() -> None:
    context = ContinuityResolver(_full_store()).resolve("CHAR_PETRICK", "legacy", 1)
    assert context.phrases == (
        "mesmo personagem CHAR_PETRICK: rosto oval face; cabelo tied back",
        "figurino travado: figurino black blazer; relógio steel chronograph",
        "locação travada: showroom Flagship; cidade São Paulo",
        "veículo travado: veículo RAM 1500; cor branco pérola",
        "voz travada: perfil de voz petrick-low-warm; emoção confident",
    )
    assert context.block() == " ".join(context.phrases)


def test_resolve_collects_the_stored_fingerprints() -> None:
    store = _full_store()
    context = ContinuityResolver(store).resolve("CHAR_PETRICK", "legacy", 1)
    assert set(context.fingerprint_map()) == set(LOCK_ORDER)
    assert context.fingerprint_map()["identity"] == store.get_lock("identity", "CHAR_PETRICK", "legacy", 1).fingerprint


def test_resolve_injects_the_persona_into_identity_without_one() -> None:
    store = FakeStore()
    identity = IdentityLock.lock("CHAR_PETRICK", face="oval face")
    payload = {key: value for key, value in identity.to_dict().items() if key != "persona_id"}
    store.put("identity", "CHAR_PETRICK", "legacy", 1, payload, identity.fingerprint)
    context = ContinuityResolver(store).resolve("CHAR_PETRICK", "legacy", 1)
    assert context.identity is not None
    assert context.identity.persona_id == "CHAR_PETRICK"


def test_resolve_keeps_the_stored_persona_when_present() -> None:
    store = FakeStore()
    identity = IdentityLock.lock("CHAR_OTHER", face="oval face")
    store.put(
        "identity", "CHAR_PETRICK", "legacy", 1,
        {**identity.to_dict(), "persona_id": "CHAR_OTHER"}, identity.fingerprint,
    )
    context = ContinuityResolver(store).resolve("CHAR_PETRICK", "legacy", 1)
    assert context.identity is not None
    assert context.identity.persona_id == "CHAR_OTHER"


# ---------------------------------------------------------------------------
# Missing locks: an empty context is valid, never an error
# ---------------------------------------------------------------------------


def test_resolve_without_a_store_reports_everything_missing() -> None:
    context = ContinuityResolver().resolve("CHAR_PETRICK", "legacy", 1)
    assert context.missing == LOCK_ORDER
    assert context.phrases == ()
    assert context.fingerprint_map() == {}
    assert context.block() == ""
    assert context.consistent is False
    assert context.to_dict()["identity"] is None


def test_resolve_with_a_partial_store_lists_only_what_is_missing() -> None:
    store = FakeStore()
    wardrobe = WardrobeLock.lock(outfit="black blazer")
    store.put("wardrobe", "CHAR_PETRICK", "legacy", 1, wardrobe.to_dict(), wardrobe.fingerprint)
    context = ContinuityResolver(store).resolve("CHAR_PETRICK", "legacy", 1)
    assert context.missing == ("identity", "location", "vehicle", "voice")
    assert context.phrases == ("figurino travado: figurino black blazer",)
    assert context.consistent is False


# ---------------------------------------------------------------------------
# Drift: stored fingerprint no longer matching the payload
# ---------------------------------------------------------------------------


def test_resolve_flags_a_lock_whose_payload_changed_behind_its_back() -> None:
    store = _full_store()
    tampered = dict(store.get_lock("wardrobe", "CHAR_PETRICK", "legacy", 1).payload)
    tampered["outfit"] = "white t-shirt"
    stored = store.get_lock("wardrobe", "CHAR_PETRICK", "legacy", 1)
    store.put("wardrobe", "CHAR_PETRICK", "legacy", 1, tampered, stored.fingerprint)
    context = ContinuityResolver(store).resolve("CHAR_PETRICK", "legacy", 1)
    assert context.drift == ("wardrobe",)
    assert context.consistent is False
    # The phrase still describes the stored payload — drift is reported, not hidden.
    assert "white t-shirt" in context.block()


def test_resolve_rejects_a_corrupt_payload_loudly() -> None:
    store = FakeStore()
    store.put("voice", "CHAR_PETRICK", "legacy", 1, {"voice_profile": 123}, "deadbeefdeadbeef")
    with pytest.raises(ContinuityValidationError):
        ContinuityResolver(store).resolve("CHAR_PETRICK", "legacy", 1)


def test_rebuild_refuses_an_unknown_lock_type() -> None:
    with pytest.raises(ContinuityValidationError, match="unknown lock type"):
        _rebuild("prop", "CHAR_PETRICK", FakeStoredLock({}, ""))


# ---------------------------------------------------------------------------
# Key validation and defaults
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad", ["", "   "])
def test_resolve_needs_an_anchor_persona(bad: str) -> None:
    with pytest.raises(ContinuityValidationError):
        ContinuityResolver(FakeStore()).resolve(bad, "legacy", 1)


def test_resolve_strips_the_persona() -> None:
    context = ContinuityResolver(FakeStore()).resolve("  CHAR_PETRICK ", "legacy", 1)
    assert context.persona_id == "CHAR_PETRICK"


@pytest.mark.parametrize("campaign", [None, "", "   "])
def test_resolve_defaults_blank_campaigns(campaign) -> None:
    context = ContinuityResolver(FakeStore()).resolve("CHAR_PETRICK", campaign, 1)
    assert context.campaign_id == "default"


@pytest.mark.parametrize("bad", [0, -2, True, "1", 1.5])
def test_resolve_refuses_invalid_episodes(bad) -> None:
    with pytest.raises(ContinuityValidationError):
        ContinuityResolver(FakeStore()).resolve("CHAR_PETRICK", "legacy", bad)


def test_resolve_treats_a_null_episode_as_the_first() -> None:
    context = ContinuityResolver(FakeStore()).resolve("CHAR_PETRICK", "legacy", None)
    assert context.episode == 1


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------


def test_context_to_dict_carries_every_snapshot_and_signal() -> None:
    context = ContinuityResolver(_full_store()).resolve("CHAR_PETRICK", "legacy", 1)
    payload = context.to_dict()
    assert payload["persona_id"] == "CHAR_PETRICK"
    assert payload["identity"]["face"] == "oval face"
    assert payload["wardrobe"]["outfit"] == "black blazer"
    assert payload["location"]["showroom"] == "Flagship"
    assert payload["vehicle"]["vehicle"] == "RAM 1500"
    assert payload["voice"]["voice_profile"] == "petrick-low-warm"
    assert len(payload["phrases"]) == 5
    assert set(payload["fingerprints"]) == set(LOCK_ORDER)
    assert payload["missing"] == []
    assert payload["drift"] == []
    assert payload["consistent"] is True
    assert payload["block"].startswith("mesmo personagem")


def test_snapshot_dict_is_what_an_episode_freezes() -> None:
    resolver = ContinuityResolver(_full_store())
    context = resolver.resolve("CHAR_PETRICK", "legacy", 1)
    snapshot = resolver.snapshot_dict(context)
    assert snapshot["persona_id"] == "CHAR_PETRICK"
    assert snapshot["episode"] == 1
    assert set(snapshot["locks"]) == set(LOCK_ORDER)
    assert snapshot["locks"]["identity"]["face"] == "oval face"
    assert snapshot["consistent"] is True


def test_snapshot_dict_of_an_empty_context_freezes_the_gaps() -> None:
    resolver = ContinuityResolver()
    snapshot = resolver.snapshot_dict(resolver.resolve("CHAR_PETRICK", "legacy", 1))
    assert snapshot["locks"] == {}
    assert snapshot["missing"] == list(LOCK_ORDER)
    assert snapshot["consistent"] is False


def test_empty_context_block_and_fingerprints() -> None:
    context = ContinuityContext(persona_id="X", campaign_id="default", episode=1)
    assert context.block() == ""
    assert context.fingerprint_map() == {}
    assert context.to_dict()["voice"] is None
