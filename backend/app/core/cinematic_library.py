"""CinematicLibrary — the reference grammar and the rules that govern it.

ETAPA 5. `knowledge_base/CINEMATIC_BIBLE.md` declares a precise visual
vocabulary — what each focal length means, what each light does, which
motivations justify a camera move, which grading rules are non-negotiable. Until
now that document was **prose that nothing in the code applied**: `StylePreset.lens`
was a free string, no preset could be checked against the Bible, and "grain is
consistent across an episode" had no meaning because no object modelled an
episode's look.

This module encodes that document as structured, queryable data plus normative
checks. Every constant below cites the sentence it comes from; nothing is
invented.

Boundaries — deliberately not duplicated:

    DirectorAgent      plain language -> intent -> style_hint   (ETAPA 2)
    StyleResolver      style_id -> technical vocabulary          (ETAPA 2)
    ShotResolver       shot code -> direction preset             (ETAPA 2)
    CinematicLibrary   what the vocabulary MEANS, and whether a
                       choice obeys the Bible                    (this file)

The library is descriptive and normative, not a recommender: it answers "what
does 135mm mean", "is this move motivated", "is this episode visually
consistent" — never "which style should I pick", which is the Director's job.

Independence: imports `contracts` only. It *reads* presets; it never builds
prompts and never touches providers.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from .contracts import ShotPreset, StylePreset

#: A focal length written as "<number>mm". The lookbehind stops "135mm" from
#: matching as 35mm.
_FOCAL_RE = re.compile(r"(?<!\d)(\d+)\s*mm", re.IGNORECASE)

# ---------------------------------------------------------------------------
# Lens language — CINEMATIC_BIBLE.md, "Lens language"
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LensProfile:
    """One focal length and what it is for, verbatim from the Bible."""

    focal_mm: int
    semantics: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["semantics"] = list(self.semantics)
        return payload


LENSES: tuple[LensProfile, ...] = (
    LensProfile(24, ("scale", "environment", "vulnerability", "architecture")),
    LensProfile(35, ("human context", "movement", "documentary intimacy")),
    LensProfile(50, ("natural perspective", "balanced hero coverage")),
    LensProfile(85, ("portrait", "luxury", "compression", "separation")),
    LensProfile(135, ("observation", "isolation", "premium editorial detail")),
)

# ---------------------------------------------------------------------------
# Framing — CINEMATIC_BIBLE.md, "Framing"
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FrameProfile:
    """What a shot size carries. "Close-up carries thought", not "close-up looks nice"."""

    name: str
    carries: str
    keywords: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["keywords"] = list(self.keywords)
        return payload


FRAMES: tuple[FrameProfile, ...] = (
    FrameProfile("establishing shot", "sets geography", ("establishing", "wide establishing", "geography")),
    FrameProfile("medium shot", "carries action", ("medium shot", "medium", "tracking medium")),
    FrameProfile("close-up", "carries thought", ("close-up", "close up", "intimate close")),
    FrameProfile("extreme close-up", "isolates a decision", ("extreme close", "macro", "razor thin")),
)


@dataclass(frozen=True)
class AngleProfile:
    """Angle is meaning, not decoration."""

    name: str
    creates: str
    keywords: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["keywords"] = list(self.keywords)
        return payload


ANGLES: tuple[AngleProfile, ...] = (
    AngleProfile("low angle", "presence", ("low angle", "low-angle", "hero angle")),
    AngleProfile("high angle", "vulnerability", ("high angle", "high-angle", "overhead", "top down")),
    AngleProfile("centered symmetry", "authority", ("centered", "centred", "symmetr", "locked tripod")),
)

# ---------------------------------------------------------------------------
# Lighting — CINEMATIC_BIBLE.md, "Lighting"
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LightingProfile:
    """What each light is for, plus any constraint the Bible attaches to it."""

    name: str
    role: str
    constraint: str = ""
    keywords: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["keywords"] = list(self.keywords)
        return payload


LIGHTS: tuple[LightingProfile, ...] = (
    LightingProfile("key light", "establishes intention", keywords=("key",)),
    LightingProfile("rim light", "separates the subject", keywords=("rim",)),
    LightingProfile("practical lights", "establish world", keywords=("practical",)),
    LightingProfile(
        "volumetric haze",
        "reveals depth",
        constraint="used to reveal depth, never as decoration",
        keywords=("volumetric", "haze", "beams", "shafts"),
    ),
)


@dataclass(frozen=True)
class TimeQuality:
    """A light quality and the tone it supports."""

    name: str
    supports: str
    keywords: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["keywords"] = list(self.keywords)
        return payload


TIME_QUALITIES: tuple[TimeQuality, ...] = (
    TimeQuality("blue hour", "reflection", ("blue hour", "blue-hour")),
    TimeQuality("hard noon", "discipline", ("hard noon", "noon", "hard directional")),
    TimeQuality("warm side light", "legacy", ("warm side", "warm practical", "warm hero")),
)

# ---------------------------------------------------------------------------
# Direction — CINEMATIC_BIBLE.md, "Direction"
#
# "Every camera movement must have motivation: reveal, approach, escape,
#  observation or transformation."
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Motivation:
    """One of the five legitimate reasons to move the camera."""

    name: str
    description: str
    keywords: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["keywords"] = list(self.keywords)
        return payload


MOTIVATIONS: tuple[Motivation, ...] = (
    Motivation(
        "reveal",
        "shows something the audience could not see",
        ("reveal", "discover", "unveil", "descending", "descend", "descent", "crane up and away"),
    ),
    Motivation(
        "approach",
        "closes distance toward the subject",
        ("push-in", "push in", "dolly", "approach", "advance", "landing", "move with the subject", "tracking"),
    ),
    Motivation(
        "escape",
        "withdraws or breaks away",
        ("pull back", "pull-back", "away", "retreat", "departure", "escape", "withdraw"),
    ),
    Motivation(
        "observation",
        "watches without intervening",
        ("orbit", "locked", "tripod", "observe", "drift", "handheld", "watch"),
    ),
    Motivation(
        "transformation",
        "changes what the frame means",
        ("transition", "whip", "morph", "rise to", "escalat"),
    ),
)

#: Phrases that describe *no movement at all*. The Bible constrains camera
#: **movement** ("every camera movement must have motivation"), so a still camera
#: has nothing to justify and the rule does not apply to it. Treating `static` as
#: an unmotivated move would flag the deliberately inert neutral fallback.
STILL_MOTIONS: frozenset[str] = frozenset({"static", "none", "locked off", ""})

#: A move that claims motivation without naming one. Better than silence, worse
#: than a named motivation, so it is attention rather than a violation.
UNNAMED_MOTIVATION_WORDS: frozenset[str] = frozenset({"motivated", "motivation"})

#: Palettes that already declare restraint satisfy "use sparingly" by saying so.
RESTRAINT_WORDS: frozenset[str] = frozenset({"restraint", "sparing", "controlled", "subtle"})

# ---------------------------------------------------------------------------
# Color grading — CINEMATIC_BIBLE.md, "Color grading"
#
# Each rule is a (name, source sentence) pair; the check lives in
# `CinematicLibrary` next to its keywords so the two cannot drift apart.
# ---------------------------------------------------------------------------

RULE_SKIN_NATURAL = "skin-natural"
RULE_PROTECT_HIGHLIGHTS = "protect-highlights"
RULE_TEAL_AMBER_SPARINGLY = "teal-amber-sparingly"
RULE_GRAIN_SUBTLE = "grain-subtle"
RULE_GRAIN_CONSISTENT = "grain-consistent-across-episode"
RULE_MOTION_MOTIVATED = "motion-motivated"
RULE_HAZE_HAS_PURPOSE = "haze-reveals-depth"
RULE_LENS_DECLARED = "lens-declared"

#: Grains the Bible would call subtle. Anything else is flagged for review.
SUBTLE_GRAINS: frozenset[str] = frozenset(
    {"none", "almost none", "clean, low", "subtle 35mm grain", "fine large-format grain", "tight digital grain"}
)

#: Highlight language that risks clipping or crushing.
HIGHLIGHT_RISK: frozenset[str] = frozenset({"crushed", "glowing", "specular", "blown", "clipped"})

#: Palettes carrying both sides of the teal-and-amber pair.
TEAL_WORDS: frozenset[str] = frozenset({"teal", "cyan", "blue"})
AMBER_WORDS: frozenset[str] = frozenset({"amber", "orange", "warm", "champagne", "gold"})

STATUS_OK = "ok"
STATUS_ATTENTION = "attention"
STATUS_VIOLATION = "violation"


@dataclass(frozen=True)
class RuleFinding:
    """The result of one normative check. Carries the sentence it enforces."""

    rule: str
    status: str
    detail: str
    source: str = "knowledge_base/CINEMATIC_BIBLE.md"

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class CinematicLibrary:
    """The reference the director consults, and the rules it enforces."""

    # ------------------------------------------------------------------ lenses

    def lenses(self) -> tuple[LensProfile, ...]:
        return LENSES

    def lens(self, focal_mm: int) -> LensProfile | None:
        return next((profile for profile in LENSES if profile.focal_mm == focal_mm), None)

    def lens_for(self, purpose: str) -> list[LensProfile]:
        """Which focal lengths serve a purpose. "isolation" -> 135mm."""

        needle = purpose.strip().casefold()
        if not needle:
            return []
        return [profile for profile in LENSES if any(needle in word for word in profile.semantics)]

    def focal_of(self, text: str) -> int | None:
        """Read the focal length out of free text ("85mm portrait" -> 85).

        Matches on a digit boundary. A plain substring test reads `"135mm"` as
        35mm, because `"35mm"` occurs inside it — which silently misreported
        SH122, a published shot whose lens is 135mm.
        """

        match = _FOCAL_RE.search(text or "")
        if not match:
            return None
        focal = int(match.group(1))
        return focal if any(profile.focal_mm == focal for profile in LENSES) else None

    # ----------------------------------------------------------------- framing

    def framing(self) -> tuple[FrameProfile, ...]:
        return FRAMES

    def angles(self) -> tuple[AngleProfile, ...]:
        return ANGLES

    def frame_of(self, text: str) -> FrameProfile | None:
        return self._match(FRAMES, text)

    def angle_of(self, text: str) -> AngleProfile | None:
        return self._match(ANGLES, text)

    # ---------------------------------------------------------------- lighting

    def lighting(self) -> tuple[LightingProfile, ...]:
        return LIGHTS

    def time_qualities(self) -> tuple[TimeQuality, ...]:
        return TIME_QUALITIES

    def light_for(self, support: str) -> TimeQuality | None:
        """Which light quality supports a tone. "legacy" -> warm side light."""

        needle = support.strip().casefold()
        if not needle:
            return None
        return next((quality for quality in TIME_QUALITIES if needle in quality.supports.casefold()), None)

    def lights_in(self, text: str) -> list[LightingProfile]:
        lowered = (text or "").casefold()
        return [
            light
            for light in LIGHTS
            if any(keyword in lowered for keyword in light.keywords)
        ]

    def qualities_in(self, text: str) -> list[TimeQuality]:
        lowered = (text or "").casefold()
        return [
            quality
            for quality in TIME_QUALITIES
            if any(keyword in lowered for keyword in quality.keywords)
        ]

    # -------------------------------------------------------------- motivation

    def motivations(self) -> tuple[Motivation, ...]:
        return MOTIVATIONS

    def motivation_of(self, motion: str) -> tuple[str, ...]:
        """Which motivations a camera move can claim.

        Empty means either "no movement declared" or "movement with no named
        motivation"; `is_still` tells the two apart.
        """

        lowered = (motion or "").strip().casefold()
        if self.is_still(motion):
            return ()
        return tuple(
            motivation.name
            for motivation in MOTIVATIONS
            if any(keyword in lowered for keyword in motivation.keywords)
        )

    def is_still(self, motion: str) -> bool:
        """True when the phrase declares no movement, so no motivation is owed."""

        return (motion or "").strip().casefold() in STILL_MOTIONS

    def claims_motivation_without_naming(self, motion: str) -> bool:
        lowered = (motion or "").casefold()
        return not self.motivation_of(motion) and any(word in lowered for word in UNNAMED_MOTIVATION_WORDS)

    def is_motivated(self, motion: str) -> bool:
        """A still camera counts as satisfied: there is no move to justify."""

        return self.is_still(motion) or bool(self.motivation_of(motion))

    # ------------------------------------------------------------------- rules

    def audit_style(self, style: StylePreset) -> list[RuleFinding]:
        """Check one style preset against the grading and direction rules."""

        findings: list[RuleFinding] = [
            self._check_grain(style.grain),
            self._check_highlights(style.contrast, style.lut),
            self._check_teal_amber(style.palette, style.lut),
            self._check_motion(style.camera_motion),
            self._check_haze(style.particles, style.lighting),
            self._check_skin(style.contrast, style.lut),
            self._check_lens_declared(style.lens),
        ]
        return findings

    def audit_shot(self, shot: ShotPreset) -> list[RuleFinding]:
        """Check one shot preset. Shots carry a camera path, not a grade."""

        return [self._check_motion(shot.camera_path), self._check_lens_declared(shot.lens)]

    def audit_library(self, styles: list[StylePreset], shots: list[ShotPreset] | None = None) -> dict[str, object]:
        """Audit the whole library and report what does not comply.

        Reporting the library's own exceptions is the point: a rule nobody
        checks against the seeds is a rule nobody follows.
        """

        style_findings = {style.style_id: self.audit_style(style) for style in styles}
        shot_findings = {shot.code: self.audit_shot(shot) for shot in (shots or [])}
        flagged = {
            identifier: [finding.to_dict() for finding in findings if finding.status != STATUS_OK]
            for identifier, findings in {**style_findings, **shot_findings}.items()
        }
        return {
            "styles_audited": len(styles),
            "shots_audited": len(shots or []),
            "rules": self.rule_names(),
            "flagged": {identifier: items for identifier, items in flagged.items() if items},
            "compliant": sorted(identifier for identifier, items in flagged.items() if not items),
        }

    def rule_names(self) -> tuple[str, ...]:
        return (
            RULE_SKIN_NATURAL,
            RULE_PROTECT_HIGHLIGHTS,
            RULE_TEAL_AMBER_SPARINGLY,
            RULE_GRAIN_SUBTLE,
            RULE_MOTION_MOTIVATED,
            RULE_HAZE_HAS_PURPOSE,
            RULE_LENS_DECLARED,
            RULE_GRAIN_CONSISTENT,
        )

    # ------------------------------------------------------- episode cohesion

    def episode_consistency(self, styles: list[StylePreset]) -> dict[str, object]:
        """"Grain is subtle and consistent across an episode."

        An episode shot in three grades is the failure this catches. Grain is the
        rule the Bible states outright, so a mismatch is a violation; LUT and
        palette drift are reported as attention because the Bible asks for
        restraint there rather than naming a single value.
        """

        if not styles:
            return {"scenes": 0, "consistent": True, "grain": [], "lut": [], "palette": [], "findings": []}

        grains = [style.grain for style in styles]
        luts = [style.lut for style in styles]
        palettes = [style.palette for style in styles]
        findings: list[RuleFinding] = []

        if len(set(grains)) > 1:
            findings.append(
                RuleFinding(
                    RULE_GRAIN_CONSISTENT,
                    STATUS_VIOLATION,
                    f"episode mixes {len(set(grains))} grain treatments: {', '.join(sorted(set(grains)))}",
                )
            )
        if len(set(luts)) > 1:
            findings.append(
                RuleFinding(
                    "grade-consistent-across-episode",
                    STATUS_ATTENTION,
                    f"episode mixes {len(set(luts))} grades",
                )
            )
        if len(set(palettes)) > 1:
            findings.append(
                RuleFinding(
                    "palette-consistent-across-episode",
                    STATUS_ATTENTION,
                    f"episode mixes {len(set(palettes))} palettes",
                )
            )

        return {
            "scenes": len(styles),
            "consistent": not any(finding.status == STATUS_VIOLATION for finding in findings),
            "grain": sorted(set(grains)),
            "lut": sorted(set(luts)),
            "palette": sorted(set(palettes)),
            "findings": [finding.to_dict() for finding in findings],
        }

    # ------------------------------------------------------------- explanation

    def explain(self, style: StylePreset) -> str:
        """Director-facing prose for a style: what it is and why it looks that way."""

        parts: list[str] = []
        focal = self.focal_of(style.lens)
        profile = self.lens(focal) if focal else None
        if profile:
            parts.append(f"{profile.focal_mm}mm for {', '.join(profile.semantics)}")
        else:
            parts.append(style.lens)

        lights = self.lights_in(style.lighting)
        if lights:
            parts.append("; ".join(f"{light.name} {light.role}" for light in lights))
        qualities = self.qualities_in(style.lighting)
        if qualities:
            parts.append("; ".join(f"{quality.name} supports {quality.supports}" for quality in qualities))

        motivations = self.motivation_of(style.camera_motion)
        parts.append(
            f"camera motivated by {', '.join(motivations)}"
            if motivations
            else "camera motion declares no motivation"
        )
        return ". ".join(parts) + "."

    # ------------------------------------------------------------------ checks

    @staticmethod
    def _match(profiles, text: str):
        lowered = (text or "").casefold()
        if not lowered:
            return None
        for profile in profiles:
            if any(keyword in lowered for keyword in profile.keywords):
                return profile
        return None

    def _check_grain(self, grain: str) -> RuleFinding:
        if (grain or "").strip().casefold() in SUBTLE_GRAINS:
            return RuleFinding(RULE_GRAIN_SUBTLE, STATUS_OK, f'"{grain}" is subtle')
        return RuleFinding(
            RULE_GRAIN_SUBTLE, STATUS_ATTENTION, f'"{grain}" is not in the subtle set'
        )

    def _check_highlights(self, contrast: str, lut: str) -> RuleFinding:
        text = f"{contrast} {lut}".casefold()
        risky = sorted(word for word in HIGHLIGHT_RISK if word in text)
        if not risky:
            return RuleFinding(RULE_PROTECT_HIGHLIGHTS, STATUS_OK, "no clipping or crushing language")
        if "protect" in text:
            return RuleFinding(RULE_PROTECT_HIGHLIGHTS, STATUS_OK, "highlights explicitly protected")
        return RuleFinding(
            RULE_PROTECT_HIGHLIGHTS,
            STATUS_ATTENTION,
            f"highlight risk from: {', '.join(risky)} — protect highlights",
        )

    def _check_teal_amber(self, palette: str, lut: str) -> RuleFinding:
        text = f"{palette} {lut}".casefold()
        teal = sorted(word for word in TEAL_WORDS if word in text)
        amber = sorted(word for word in AMBER_WORDS if word in text)
        if teal and amber and not any(word in text for word in RESTRAINT_WORDS):
            return RuleFinding(
                RULE_TEAL_AMBER_SPARINGLY,
                STATUS_ATTENTION,
                f"both sides of the pair present ({', '.join(teal)} / {', '.join(amber)}) — use sparingly",
            )
        return RuleFinding(RULE_TEAL_AMBER_SPARINGLY, STATUS_OK, "palette does not lean on the teal-and-amber pair")

    def _check_motion(self, motion: str) -> RuleFinding:
        motivations = self.motivation_of(motion)
        if motivations:
            return RuleFinding(RULE_MOTION_MOTIVATED, STATUS_OK, f"motivated by {', '.join(motivations)}")
        if self.is_still(motion):
            return RuleFinding(
                RULE_MOTION_MOTIVATED,
                STATUS_OK,
                f'"{motion}" declares no movement, so no motivation is owed',
            )
        if self.claims_motivation_without_naming(motion):
            return RuleFinding(
                RULE_MOTION_MOTIVATED,
                STATUS_ATTENTION,
                f'"{motion}" claims motivation without naming one '
                "(reveal, approach, escape, observation or transformation)",
            )
        return RuleFinding(
            RULE_MOTION_MOTIVATED,
            STATUS_VIOLATION,
            f'"{motion}" declares no motivation (reveal, approach, escape, observation or transformation)',
        )

    def _check_haze(self, particles: str, lighting: str) -> RuleFinding:
        text = f"{particles} {lighting}".casefold()
        haze = next((light for light in LIGHTS if light.name == "volumetric haze"), None)
        if haze is None or not any(keyword in text for keyword in haze.keywords):
            return RuleFinding(RULE_HAZE_HAS_PURPOSE, STATUS_OK, "no haze declared")
        purposeful = any(word in text for word in ("depth", "reveal", "shaft", "beam", "separation"))
        if purposeful:
            return RuleFinding(RULE_HAZE_HAS_PURPOSE, STATUS_OK, "haze reveals depth")
        return RuleFinding(
            RULE_HAZE_HAS_PURPOSE,
            STATUS_ATTENTION,
            "haze declared without depth or reveal language — the Bible forbids decorative haze",
        )

    def _check_skin(self, contrast: str, lut: str) -> RuleFinding:
        text = f"{contrast} {lut}".casefold()
        if "natural skin" in text or "skin" in text:
            return RuleFinding(RULE_SKIN_NATURAL, STATUS_OK, "skin treatment declared")
        return RuleFinding(
            RULE_SKIN_NATURAL,
            STATUS_OK,
            "no skin-altering grade declared, so natural skin stands",
        )

    def _check_lens_declared(self, lens: str) -> RuleFinding:
        focal = self.focal_of(lens)
        if focal is None:
            return RuleFinding(RULE_LENS_DECLARED, STATUS_ATTENTION, f'"{lens}" names no known focal length')
        return RuleFinding(RULE_LENS_DECLARED, STATUS_OK, f"{focal}mm is in the lens language")
