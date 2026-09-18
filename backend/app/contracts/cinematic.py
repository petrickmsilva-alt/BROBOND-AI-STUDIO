"""Cinematic contracts — the style and shot vocabulary.

A style carries the whole technical vocabulary so nobody has to type a
prompt; a shot is a reusable direction preset addressed by a stable code.
Both are read through a protocol, so the library can be seeded, persisted
or injected without the Core noticing.

PR010.0 froze this vocabulary. It was moved here verbatim from
`app/core/contracts.py`, which now re-exports it: the objects are the *same*
objects, so `app.core.contracts.StylePreset is app.contracts.StylePreset`. A module
that needs this vocabulary imports it; it never restates it.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Protocol, runtime_checkable

@dataclass(frozen=True)
class StylePreset:
    """A cinematic library entry (ETAPA 5).

    The user picks a style; the style carries the whole technical vocabulary so
    nobody has to type a prompt.
    """

    style_id: str
    name: str
    lens: str
    lut: str
    lighting: str
    contrast: str
    grain: str
    camera_motion: str
    particles: str
    fps: int
    palette: str = ""
    description: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

@dataclass(frozen=True)
class ShotPreset:
    """A shot library entry (ETAPA 6).

    A shot is a reusable direction preset, not a prompt blob
    (knowledge_base/SHOT_LIBRARY.md).
    """

    code: str
    name: str
    camera_path: str
    speed: str
    lens: str
    focus: str
    shake: str
    depth: str
    intention: str = ""
    # ETAPA 6 — knowledge_base/SHOT_LIBRARY.md "Expansion policy": "New shots
    # require code, name, lens, frame, movement, lighting, emotional intention
    # and continuity notes." Added with defaults so the ten published presets
    # keep constructing unchanged.
    frame: str = ""
    lighting: str = ""
    continuity: str = ""
    family: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

@runtime_checkable
class StyleSource(Protocol):
    def fetch(self, style_id: str) -> StylePreset | None:
        ...

    def search(self, query: str = "") -> list[StylePreset]:
        ...

@runtime_checkable
class ShotSource(Protocol):
    def fetch(self, code: str) -> ShotPreset | None:
        ...

    def search(self, query: str = "") -> list[ShotPreset]:
        ...
