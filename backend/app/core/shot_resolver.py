"""ShotResolver — the shot library.

Responsibility: resolve a stable shot code into its direction preset (camera
path, speed, lens, focus, shake, depth). "A shot is a reusable direction
preset, not a prompt blob" — knowledge_base/SHOT_LIBRARY.md.

Independence: imports `contracts` only.

Identifier policy: the codes below are the ones already published in
knowledge_base/SHOT_LIBRARY.md and seeded in backend/app/knowledge.py. Those
documents state that shot codes are *stable identifiers*, so this resolver
reuses them verbatim instead of renumbering. Lookup accepts a code or a name.
"""
from __future__ import annotations

from .contracts import ShotPreset, ShotSource

#: Shot codes already published in the repository. Preserved exactly.
SEED_SHOTS: tuple[ShotPreset, ...] = (
    ShotPreset(
        code="SH001",
        name="Hero Walk",
        camera_path="low-angle tracking, moving with the subject",
        speed="steady walking pace",
        lens="50mm",
        focus="subject locked, background soft",
        shake="none, stabilised",
        depth="medium, subject separated from ground plane",
        intention="confident forward motion",
    ),
    ShotPreset(
        code="SH014",
        name="Close Eyes",
        camera_path="slow push-in to intimate close-up",
        speed="very slow",
        lens="85mm",
        focus="razor thin on the eyes",
        shake="none",
        depth="very shallow",
        intention="internal thought, withheld emotion",
    ),
    ShotPreset(
        code="SH032",
        name="Drone Reveal",
        camera_path="aerial establishing, crane reveal descending to subject",
        speed="fast reveal then settle",
        lens="24mm",
        focus="deep, geography readable",
        shake="none, gimbal",
        depth="deep",
        intention="geographic scale, arrival",
    ),
    ShotPreset(
        code="SH051",
        name="Orbit 360",
        camera_path="full orbit around a locked subject",
        speed="constant, one full revolution",
        lens="35mm",
        focus="subject locked throughout",
        shake="none",
        depth="medium, strong parallax",
        intention="parallax reveal, scrutiny",
    ),
    ShotPreset(
        code="SH089",
        name="Slow Rain",
        camera_path="slow drift, backlit",
        speed="slow motion",
        lens="85mm",
        focus="shallow rain depth, subject crisp",
        shake="none",
        depth="very shallow",
        intention="reflection, suspension of time",
    ),
    ShotPreset(
        code="SH120",
        name="Luxury Entrance",
        camera_path="symmetrical dolly-in through architecture",
        speed="measured",
        lens="35mm",
        focus="subject centred, architecture sharp",
        shake="none, dolly",
        depth="deep, layered planes",
        intention="authority, arrival into a controlled world",
    ),
    ShotPreset(
        code="SH121",
        name="Shoulder Pursuit",
        camera_path="handheld tracking over the shoulder",
        speed="urgent, matching the subject",
        lens="50mm",
        focus="subject, with breathing focus drift",
        shake="motivated handheld",
        depth="medium shallow",
        intention="motivated urgency, pursuit",
    ),
    ShotPreset(
        code="SH122",
        name="Detail Insert",
        camera_path="deliberate reveal of a single object",
        speed="slow, precise",
        lens="135mm",
        focus="macro-like on the object",
        shake="none",
        depth="extremely shallow",
        intention="object significance, evidence",
    ),
    ShotPreset(
        code="SH123",
        name="Crane Departure",
        camera_path="crane up and away from the subject",
        speed="accelerating lift",
        lens="24mm",
        focus="deep, releasing the subject into the frame",
        shake="none, crane",
        depth="deep",
        intention="emotional release, ending",
    ),
    ShotPreset(
        code="SH124",
        name="Static Authority",
        camera_path="locked tripod, centred frame",
        speed="static",
        lens="50mm",
        focus="even, subject and context readable",
        shake="none",
        depth="medium deep",
        intention="control, judgement, stillness",
    ),
)


class SeedShotSource:
    """Default in-memory `ShotSource` backed by the published shot codes."""

    def __init__(self, shots: tuple[ShotPreset, ...] = SEED_SHOTS) -> None:
        self._by_code: dict[str, ShotPreset] = {shot.code: shot for shot in shots}
        self._by_name: dict[str, ShotPreset] = {shot.name.casefold(): shot for shot in shots}

    def register(self, shot: ShotPreset) -> ShotPreset:
        self._by_code[shot.code] = shot
        self._by_name[shot.name.casefold()] = shot
        return shot

    def fetch(self, code: str) -> ShotPreset | None:
        return self._by_code.get(code.strip().upper()) or self._by_name.get(code.strip().casefold())

    def search(self, query: str = "") -> list[ShotPreset]:
        if not query:
            return list(self._by_code.values())
        needle = query.strip().casefold()
        return [
            shot
            for shot in self._by_code.values()
            if needle in shot.code.casefold() or needle in shot.name.casefold() or needle in shot.intention.casefold()
        ]


class ShotResolver:
    """Resolves shot codes into direction presets."""

    def __init__(self, source: ShotSource | None = None) -> None:
        self._source: ShotSource = source or SeedShotSource()

    def resolve(self, code: str | None) -> ShotPreset | None:
        """Return the preset for a code or name, or None when unknown.

        Unlike styles, an unknown shot must NOT silently fall back: inventing
        camera language the director never asked for is worse than omitting it.
        """

        if not code:
            return None
        return self._source.fetch(code)

    def catalog(self, query: str = "") -> list[ShotPreset]:
        """Full library, optionally filtered. Feeds the visual shot browser
        required by ETAPA 6, so a user never has to type a shot code."""

        return self._source.search(query)

    def count(self, query: str = "") -> int:
        return len(self.catalog(query))

    def is_known(self, code: str | None) -> bool:
        return bool(code) and self._source.fetch(code) is not None

    # -------------------------------------------------------------- vocabulary

    def camera_phrase(self, shot: ShotPreset | None) -> str:
        if shot is None:
            return ""
        return ", ".join(part for part in (shot.name.lower(), shot.camera_path, shot.lens) if part)

    def lens_phrase(self, shot: ShotPreset | None) -> str:
        if shot is None:
            return ""
        return ", ".join(part for part in (shot.lens, shot.focus, shot.depth and f"{shot.depth} depth of field") if part)

    def motion_phrase(self, shot: ShotPreset | None) -> str:
        if shot is None:
            return ""
        return ", ".join(part for part in (shot.speed, shot.shake) if part and part != "none")

    def describe(self, shot: ShotPreset) -> str:
        """Full direction line, as shown in the visual shot browser (ETAPA 6)."""

        return (
            f"{shot.code} {shot.name} — {shot.camera_path}; {shot.lens}; {shot.focus}; "
            f"speed {shot.speed}; shake {shot.shake}; {shot.depth} depth. {shot.intention}."
        )
