"""MoodEngine — resolves human mood language into internal film presets."""
from __future__ import annotations

import re

from .mood_config import DEFAULT_MOOD, MOOD_ALIASES, MOOD_PRESETS, MoodPreset

_TOKEN_PATTERN = re.compile(r"[a-zà-öø-ÿ0-9]+", re.IGNORECASE)


class MoodEngine:
    """Deterministic mood resolver for the Director AI Engine."""

    def __init__(self, presets: dict[str, MoodPreset] | None = None) -> None:
        self._presets = presets or MOOD_PRESETS

    def presets(self) -> tuple[MoodPreset, ...]:
        """Return all internal presets in configuration order."""

        return tuple(self._presets.values())

    def resolve(self, mood: str | None = None, *, user_intent: str = "") -> MoodPreset:
        """Resolve an explicit mood, infer one from intent, or return default."""

        explicit = self._lookup(mood or "")
        if explicit is not None:
            return explicit

        inferred = self.detect(user_intent)
        if inferred is not None:
            return inferred

        return self._presets[DEFAULT_MOOD.casefold()]

    def detect(self, user_intent: str) -> MoodPreset | None:
        """Infer a mood from human language without calling an LLM."""

        for token in _TOKEN_PATTERN.findall(user_intent.casefold()):
            found = self._lookup(token)
            if found is not None:
                return found
        return None

    def describe(self, preset: MoodPreset) -> str:
        """Single style line consumed by the prompt compiler and UI."""

        return "; ".join(
            (
                preset.lut,
                preset.contrast,
                preset.lighting,
                preset.temperature,
                preset.rhythm,
                preset.particles,
            )
        )

    def _lookup(self, value: str) -> MoodPreset | None:
        key = value.strip().casefold()
        if not key:
            return None
        preset = self._presets.get(key)
        if preset is not None:
            return preset
        alias = MOOD_ALIASES.get(key)
        return self._presets.get(alias.casefold()) if alias else None
