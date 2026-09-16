"""V3.2 — the five continuity locks and the package kernel.

Unit tests over frozen snapshots: validation rules, fingerprint
determinism, verify, cinematic phrases and persisted-payload round-trips.
No database, no HTTP — the locks are framework-free.
"""
from __future__ import annotations

import re

import pytest

from app.continuity import (
    IDENTITY_FIELDS,
    LOCATION_FIELDS,
    LOCATION_VENUES,
    VEHICLE_FIELDS,
    VOICE_FIELDS,
    WARDROBE_FIELDS,
    ContinuityValidationError,
    IdentityLock,
    LocationLock,
    VehicleLock,
    VoiceLock,
    WardrobeLock,
    clean_field,
    fingerprint_for,
    normalize_campaign,
    normalize_episode,
    normalize_persona_id,
)

HEX16 = re.compile(r"^[0-9a-f]{16}$")


# ---------------------------------------------------------------------------
# Kernel: fingerprint + key normalisation (identity_lock hosts each exactly once)
# ---------------------------------------------------------------------------


def test_fingerprint_is_sixteen_hex_and_deterministic() -> None:
    first = fingerprint_for(("oval face", "tied back"))
    second = fingerprint_for(("oval face", "tied back"))
    assert first == second
    assert HEX16.match(first)


def test_fingerprint_ignores_case_and_surrounding_space() -> None:
    assert fingerprint_for((" Barba Curta ",)) == fingerprint_for(("barba curta",))


def test_fingerprint_moves_on_any_other_change() -> None:
    assert fingerprint_for(("barba curta",)) != fingerprint_for(("barba longa",))


def test_fingerprint_does_not_confuse_field_boundaries() -> None:
    assert fingerprint_for(("ab", "c")) != fingerprint_for(("a", "bc"))


@pytest.mark.parametrize("bad", ["", "   ", None, 123, ["x"]])
def test_normalize_persona_id_refuses_blank_or_non_string(bad) -> None:
    with pytest.raises(ContinuityValidationError):
        normalize_persona_id(bad)


def test_normalize_persona_id_strips() -> None:
    assert normalize_persona_id("  CHAR_PETRICK ") == "CHAR_PETRICK"


def test_normalize_campaign_defaults_blanks_to_default() -> None:
    assert normalize_campaign(None) == "default"
    assert normalize_campaign("") == "default"
    assert normalize_campaign("   ") == "default"


def test_normalize_campaign_strips() -> None:
    assert normalize_campaign("  legacy ") == "legacy"


@pytest.mark.parametrize("bad", [123, ["x"], {"c": 1}])
def test_normalize_campaign_refuses_non_string(bad) -> None:
    with pytest.raises(ContinuityValidationError):
        normalize_campaign(bad)


def test_normalize_episode_none_is_the_campaign_default() -> None:
    assert normalize_episode(None) is None


def test_normalize_episode_accepts_positive_ints() -> None:
    assert normalize_episode(1) == 1
    assert normalize_episode(12) == 12


@pytest.mark.parametrize("bad", [0, -1, True, False, "1", 1.0, [1]])
def test_normalize_episode_refuses_anything_else(bad) -> None:
    with pytest.raises(ContinuityValidationError):
        normalize_episode(bad)


def test_clean_field_strips_strings_and_refuses_the_rest() -> None:
    assert clean_field("  x ", "face") == "x"
    with pytest.raises(ContinuityValidationError):
        clean_field(123, "face")
    with pytest.raises(ContinuityValidationError):
        clean_field(None, "face")


# ---------------------------------------------------------------------------
# Identity Lock
# ---------------------------------------------------------------------------


def test_identity_fields_are_the_six_frozen_attributes() -> None:
    assert IDENTITY_FIELDS == ("face", "hair", "beard", "body", "skin", "age_appearance")


def test_identity_lock_freezes_and_fingerprints() -> None:
    snapshot = IdentityLock.lock(
        "CHAR_PETRICK",
        face="oval face",
        hair="tied back",
        beard="short beard",
        body="athletic build",
        skin="warm brown",
        age_appearance="50 years old",
    )
    assert snapshot.persona_id == "CHAR_PETRICK"
    assert snapshot.fields() == (
        "oval face",
        "tied back",
        "short beard",
        "athletic build",
        "warm brown",
        "50 years old",
    )
    assert HEX16.match(snapshot.fingerprint)
    assert snapshot.fingerprint == fingerprint_for(snapshot.fields())


def test_identity_lock_strips_everything() -> None:
    snapshot = IdentityLock.lock("  CHAR_PETRICK ", face="  oval face ")
    assert (snapshot.persona_id, snapshot.face) == ("CHAR_PETRICK", "oval face")


def test_identity_lock_needs_a_persona() -> None:
    with pytest.raises(ContinuityValidationError):
        IdentityLock.lock("   ", face="oval face")


def test_identity_lock_certifies_but_never_invents() -> None:
    with pytest.raises(ContinuityValidationError, match="at least one defined attribute"):
        IdentityLock.lock("CHAR_GHOST")


def test_identity_lock_refuses_non_string_fields() -> None:
    with pytest.raises(ContinuityValidationError):
        IdentityLock.lock("CHAR_PETRICK", face=123)  # type: ignore[arg-type]


def test_identity_fingerprint_of_recomputes() -> None:
    snapshot = IdentityLock.lock("CHAR_PETRICK", face="oval face")
    assert IdentityLock.fingerprint_of(snapshot) == snapshot.fingerprint


def test_identity_verify_accepts_the_locked_fields() -> None:
    snapshot = IdentityLock.lock("CHAR_PETRICK", face="oval face", hair="tied back")
    assert IdentityLock.verify(snapshot, face="oval face", hair="tied back") is True
    # Case and space do not move the fingerprint.
    assert IdentityLock.verify(snapshot, face=" Oval Face ", hair="TIED BACK") is True


def test_identity_verify_rejects_a_changed_field() -> None:
    snapshot = IdentityLock.lock("CHAR_PETRICK", face="oval face", hair="tied back")
    assert IdentityLock.verify(snapshot, face="oval face", hair="shaved") is False


def test_identity_verify_ignores_unknown_keywords() -> None:
    snapshot = IdentityLock.lock("CHAR_PETRICK", face="oval face")
    assert IdentityLock.verify(snapshot, face="oval face", episode=3) is True  # type: ignore[arg-type]


def test_identity_verify_refuses_non_string_candidates() -> None:
    snapshot = IdentityLock.lock("CHAR_PETRICK", face="oval face")
    with pytest.raises(ContinuityValidationError):
        IdentityLock.verify(snapshot, face=123)  # type: ignore[arg-type]


def test_identity_phrase_names_every_defined_part() -> None:
    snapshot = IdentityLock.lock(
        "CHAR_PETRICK", face="oval face", hair="tied back", age_appearance="50 years old"
    )
    assert IdentityLock.phrase(snapshot) == (
        "mesmo personagem CHAR_PETRICK: rosto oval face; cabelo tied back; aparência de 50 years old"
    )


def test_identity_phrase_skips_blank_parts() -> None:
    snapshot = IdentityLock.lock("CHAR_PETRICK", beard="short beard")
    assert IdentityLock.phrase(snapshot) == "mesmo personagem CHAR_PETRICK: barba short beard"


def test_identity_phrase_without_parts_is_still_anchored() -> None:
    snapshot = IdentityLock.from_dict({"persona_id": "CHAR_GHOST"})
    assert IdentityLock.phrase(snapshot) == "mesmo personagem CHAR_GHOST"


def test_identity_from_dict_round_trip() -> None:
    snapshot = IdentityLock.lock("CHAR_PETRICK", face="oval face", skin="warm brown")
    rebuilt = IdentityLock.from_dict(
        {"persona_id": "CHAR_PETRICK", "face": "oval face", "skin": "warm brown"},
        fingerprint=snapshot.fingerprint,
    )
    assert rebuilt == snapshot
    assert rebuilt.to_dict()["fingerprint"] == snapshot.fingerprint


def test_identity_from_dict_ignores_unknown_keys() -> None:
    rebuilt = IdentityLock.from_dict({"persona_id": "X", "face": "f", "future": "ignored"})
    assert rebuilt.face == "f"


def test_identity_from_dict_refuses_non_objects() -> None:
    for bad in ("x", None, [("face", "f")]):
        with pytest.raises(ContinuityValidationError):
            IdentityLock.from_dict(bad)  # type: ignore[arg-type]


def test_identity_from_dict_refuses_non_string_fields() -> None:
    with pytest.raises(ContinuityValidationError):
        IdentityLock.from_dict({"face": 123})


def test_identity_from_dict_tolerates_non_string_meta() -> None:
    rebuilt = IdentityLock.from_dict({"persona_id": 123, "face": "f"}, fingerprint=456)  # type: ignore[arg-type]
    assert (rebuilt.persona_id, rebuilt.fingerprint) == ("", "")


# ---------------------------------------------------------------------------
# Wardrobe Lock
# ---------------------------------------------------------------------------


def test_wardrobe_fields_are_the_sprint_contract() -> None:
    assert WARDROBE_FIELDS == ("outfit", "accessories", "colors", "shoes", "watch")


def test_wardrobe_lock_freezes_and_fingerprints() -> None:
    snapshot = WardrobeLock.lock(
        outfit="black blazer",
        accessories="silver chain",
        colors="black and gold",
        shoes="chelsea boots",
        watch="steel chronograph",
    )
    assert snapshot.fields() == (
        "black blazer",
        "silver chain",
        "black and gold",
        "chelsea boots",
        "steel chronograph",
    )
    assert HEX16.match(snapshot.fingerprint)
    assert WardrobeLock.fingerprint_of(snapshot) == snapshot.fingerprint


def test_wardrobe_lock_requires_an_outfit() -> None:
    with pytest.raises(ContinuityValidationError, match="requires an outfit"):
        WardrobeLock.lock(accessories="silver chain")


def test_wardrobe_lock_strips_and_refuses_non_strings() -> None:
    assert WardrobeLock.lock(outfit="  blazer ").outfit == "blazer"
    with pytest.raises(ContinuityValidationError):
        WardrobeLock.lock(outfit=123)  # type: ignore[arg-type]


def test_wardrobe_verify_and_phrase() -> None:
    snapshot = WardrobeLock.lock(outfit="black blazer", watch="steel chronograph")
    assert WardrobeLock.verify(snapshot, outfit="black blazer", watch="steel chronograph") is True
    assert WardrobeLock.verify(snapshot, outfit="white t-shirt") is False
    assert WardrobeLock.phrase(snapshot) == (
        "figurino travado: figurino black blazer; relógio steel chronograph"
    )


def test_wardrobe_phrase_without_parts() -> None:
    assert WardrobeLock.phrase(WardrobeLock.from_dict({})) == "figurino travado"


def test_wardrobe_from_dict_round_trip_and_guards() -> None:
    snapshot = WardrobeLock.lock(outfit="black blazer", colors="black")
    rebuilt = WardrobeLock.from_dict(
        {"outfit": "black blazer", "colors": "black", "future": 1},
        fingerprint=snapshot.fingerprint,
    )
    assert rebuilt == snapshot
    assert rebuilt.to_dict()["outfit"] == "black blazer"
    with pytest.raises(ContinuityValidationError):
        WardrobeLock.from_dict("x")  # type: ignore[arg-type]
    with pytest.raises(ContinuityValidationError):
        WardrobeLock.from_dict({"outfit": 123})
    assert WardrobeLock.from_dict({}, fingerprint=123).fingerprint == ""  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Location Lock
# ---------------------------------------------------------------------------


def test_location_fields_and_venues_are_the_sprint_contract() -> None:
    assert LOCATION_FIELDS == ("showroom", "studio", "street", "city", "base_lighting")
    assert LOCATION_VENUES == ("showroom", "studio", "street")


def test_location_lock_freezes_and_fingerprints() -> None:
    snapshot = LocationLock.lock(
        showroom="BROBOND Flagship",
        studio="",
        street="",
        city="São Paulo",
        base_lighting="warm tungsten",
    )
    assert snapshot.fields() == ("BROBOND Flagship", "", "", "São Paulo", "warm tungsten")
    assert HEX16.match(snapshot.fingerprint)
    assert LocationLock.fingerprint_of(snapshot) == snapshot.fingerprint


@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {"city": "São Paulo"},
        {"city": "São Paulo", "base_lighting": "warm tungsten"},
        {"showroom": "  "},
    ],
)
def test_location_lock_requires_a_venue_not_an_address(kwargs) -> None:
    with pytest.raises(ContinuityValidationError, match="at least one venue"):
        LocationLock.lock(**kwargs)


@pytest.mark.parametrize("venue", ["showroom", "studio", "street"])
def test_location_lock_accepts_any_single_venue(venue: str) -> None:
    assert getattr(LocationLock.lock(**{venue: "set"}), venue) == "set"


def test_location_lock_strips_and_refuses_non_strings() -> None:
    assert LocationLock.lock(studio="  A ").studio == "A"
    with pytest.raises(ContinuityValidationError):
        LocationLock.lock(studio=123)  # type: ignore[arg-type]


def test_location_verify_and_phrase() -> None:
    snapshot = LocationLock.lock(studio="Studio B", city="Lisboa", base_lighting="blue hour")
    assert LocationLock.verify(snapshot, studio="Studio B", city="Lisboa", base_lighting="blue hour") is True
    assert LocationLock.verify(snapshot, studio="Studio C") is False
    assert LocationLock.phrase(snapshot) == (
        "locação travada: estúdio Studio B; cidade Lisboa; luz base blue hour"
    )


def test_location_phrase_without_parts() -> None:
    assert LocationLock.phrase(LocationLock.from_dict({})) == "locação travada"


def test_location_from_dict_round_trip_and_guards() -> None:
    snapshot = LocationLock.lock(showroom="Flagship", city="São Paulo")
    rebuilt = LocationLock.from_dict(
        {"showroom": "Flagship", "city": "São Paulo", "future": 1},
        fingerprint=snapshot.fingerprint,
    )
    assert rebuilt == snapshot
    assert rebuilt.to_dict()["showroom"] == "Flagship"
    with pytest.raises(ContinuityValidationError):
        LocationLock.from_dict([])  # type: ignore[arg-type]
    with pytest.raises(ContinuityValidationError):
        LocationLock.from_dict({"city": 123})
    assert LocationLock.from_dict({}, fingerprint=None).fingerprint == ""  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Vehicle Lock
# ---------------------------------------------------------------------------


def test_vehicle_fields_are_the_sprint_contract() -> None:
    assert VEHICLE_FIELDS == ("vehicle", "color", "plate", "wheels", "finish")


def test_vehicle_lock_freezes_and_fingerprints() -> None:
    snapshot = VehicleLock.lock(
        vehicle="RAM 1500",
        color="branco pérola",
        plate="ABC1D23",
        wheels="22 graphite",
        finish="matte PPF",
    )
    assert snapshot.fields() == ("RAM 1500", "branco pérola", "ABC1D23", "22 graphite", "matte PPF")
    assert HEX16.match(snapshot.fingerprint)
    assert VehicleLock.fingerprint_of(snapshot) == snapshot.fingerprint


def test_vehicle_plate_is_optional_but_model_and_color_are_not() -> None:
    assert VehicleLock.lock(vehicle="RAM 1500", color="black").plate == ""
    with pytest.raises(ContinuityValidationError, match="requires a vehicle"):
        VehicleLock.lock(color="black")
    with pytest.raises(ContinuityValidationError, match="requires a color"):
        VehicleLock.lock(vehicle="RAM 1500")


def test_vehicle_lock_strips_and_refuses_non_strings() -> None:
    assert VehicleLock.lock(vehicle="  RAM ", color=" black ").vehicle == "RAM"
    with pytest.raises(ContinuityValidationError):
        VehicleLock.lock(vehicle="RAM", color=123)  # type: ignore[arg-type]


def test_vehicle_verify_and_phrase() -> None:
    snapshot = VehicleLock.lock(vehicle="RAM 1500", color="branco pérola", plate="ABC1D23")
    assert VehicleLock.verify(snapshot, vehicle="RAM 1500", color="branco pérola", plate="ABC1D23") is True
    assert VehicleLock.verify(snapshot, vehicle="RAM 1500", color="preto") is False
    assert VehicleLock.phrase(snapshot) == (
        "veículo travado: veículo RAM 1500; cor branco pérola; placa ABC1D23"
    )


def test_vehicle_phrase_without_parts() -> None:
    assert VehicleLock.phrase(VehicleLock.from_dict({})) == "veículo travado"


def test_vehicle_from_dict_round_trip_and_guards() -> None:
    snapshot = VehicleLock.lock(vehicle="RAM 1500", color="black", wheels="22 graphite")
    rebuilt = VehicleLock.from_dict(
        {"vehicle": "RAM 1500", "color": "black", "wheels": "22 graphite", "future": 1},
        fingerprint=snapshot.fingerprint,
    )
    assert rebuilt == snapshot
    assert rebuilt.to_dict()["vehicle"] == "RAM 1500"
    with pytest.raises(ContinuityValidationError):
        VehicleLock.from_dict(None)  # type: ignore[arg-type]
    with pytest.raises(ContinuityValidationError):
        VehicleLock.from_dict({"vehicle": 123})
    assert VehicleLock.from_dict({}, fingerprint=["x"]).fingerprint == ""  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Voice Lock
# ---------------------------------------------------------------------------


def test_voice_fields_are_the_sprint_contract() -> None:
    assert VOICE_FIELDS == ("voice_profile", "default_emotion", "speed", "intensity")


def test_voice_lock_freezes_and_fingerprints() -> None:
    snapshot = VoiceLock.lock(
        voice_profile="petrick-low-warm",
        default_emotion="confident",
        speed="1.0x",
        intensity="high",
    )
    assert snapshot.fields() == ("petrick-low-warm", "confident", "1.0x", "high")
    assert HEX16.match(snapshot.fingerprint)
    assert VoiceLock.fingerprint_of(snapshot) == snapshot.fingerprint


def test_voice_lock_requires_a_profile() -> None:
    with pytest.raises(ContinuityValidationError, match="requires a voice profile"):
        VoiceLock.lock(default_emotion="confident")


def test_voice_lock_strips_and_refuses_non_strings() -> None:
    assert VoiceLock.lock(voice_profile="  v ").voice_profile == "v"
    with pytest.raises(ContinuityValidationError):
        VoiceLock.lock(voice_profile=123)  # type: ignore[arg-type]


def test_voice_verify_and_phrase() -> None:
    snapshot = VoiceLock.lock(voice_profile="petrick-low-warm", default_emotion="confident")
    assert VoiceLock.verify(snapshot, voice_profile="petrick-low-warm", default_emotion="confident") is True
    assert VoiceLock.verify(snapshot, voice_profile="other") is False
    assert VoiceLock.phrase(snapshot) == (
        "voz travada: perfil de voz petrick-low-warm; emoção confident"
    )


def test_voice_phrase_without_parts() -> None:
    assert VoiceLock.phrase(VoiceLock.from_dict({})) == "voz travada"


def test_voice_from_dict_round_trip_and_guards() -> None:
    snapshot = VoiceLock.lock(voice_profile="v", speed="1.0x")
    rebuilt = VoiceLock.from_dict(
        {"voice_profile": "v", "speed": "1.0x", "future": 1},
        fingerprint=snapshot.fingerprint,
    )
    assert rebuilt == snapshot
    assert rebuilt.to_dict()["voice_profile"] == "v"
    with pytest.raises(ContinuityValidationError):
        VoiceLock.from_dict(42)  # type: ignore[arg-type]
    with pytest.raises(ContinuityValidationError):
        VoiceLock.from_dict({"speed": 123})
    assert VoiceLock.from_dict({}, fingerprint={"f": 1}).fingerprint == ""  # type: ignore[arg-type]
