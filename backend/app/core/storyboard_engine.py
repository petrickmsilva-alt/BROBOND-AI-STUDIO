"""StoryboardEngine — cast, chain and validate a shot sequence.

ETAPA 8. Until now a storyboard was four free-text camera phrases cycling on a
ladder:

    SceneBeat(camera="wide establishing shot, coherent camera movement",
              motion="motivated by the beat",
              lighting="consistent blue-hour lighting across the sequence",
              shot_code=None)                     # <- never populated

Three things followed from that, all verified before this module was written:

1. **`shot_code` was never set.** The 300-shot library built in ETAPA 6 was
   unreachable from the storyboard, so every scene said "wide establishing
   shot" instead of casting `SH002 City Wakes` with its real lens, lighting and
   continuity note.
2. **Lighting was one fixed string** on every beat, whatever the style or scene.
3. **The Director's own motion failed the Director's own grammar.**
   `"motivated by the beat"` is exactly what ETAPA 5 flags as *claiming
   motivation without naming one*.

This module fixes all three structurally, without editing `DirectorAgent`: a
storyboard **casts real shots**, so lens, lighting, movement and continuity come
from the library rather than from a placeholder string.

Boundaries — nothing here is duplicated:

    DirectorAgent       beats: objective, emotion, duration        (ETAPA 2)
    ShotLibrary         the 300 direction presets                  (ETAPA 6)
    CinematicLibrary    grammar and the rules                      (ETAPA 5)
    PromptCompiler      the only place prompt text is produced     (ETAPA 2)
    StoryboardEngine    which shot plays which beat, in what order,
                        and whether the sequence holds together    (this file)

The engine sequences. It does not invent direction, hold shots, own grammar or
write prompts.

Independence: imports `contracts`, the three libraries above and nothing else.
"""
from __future__ import annotations

from dataclasses import dataclass

from .cinematic_library import CinematicLibrary
from .contracts import SceneBeat, ShotPreset
from .director_agent import DirectorAgent
from .shot_library import ShotLibrary

#: Canonical five-beat arc per detected format. Opens on geography, closes on
#: resolution; the middle carries whatever the format is actually about. A
#: product film climaxes on the product, a narrative film on tension.
ARC_BY_FORMAT: dict[str, tuple[str, ...]] = {
    "commercial": ("establishing", "introduction", "product", "product", "resolution"),
    "fashion": ("establishing", "introduction", "fashion", "fashion", "resolution"),
    "film": ("establishing", "introduction", "action", "tension", "resolution"),
    "reels": ("establishing", "action", "action", "tension", "resolution"),
    "story": ("establishing", "introduction", "intimacy", "intimacy", "resolution"),
    "documentary": ("establishing", "documentary", "documentary", "documentary", "resolution"),
}

#: Arc used when the format is not one the Director recognises.
DEFAULT_ARC: tuple[str, ...] = ("establishing", "introduction", "action", "tension", "resolution")

#: Transition beats can come from these families; they bridge rather than carry.
TRANSITION_FAMILIES: frozenset[str] = frozenset({"transition", "atmosphere"})

#: A sequence shorter than this cannot carry an arc.
MIN_SCENES = 2

#: Runtime guard, in seconds. Long enough for a trailer, short enough that a
#: runaway scene count is caught.
MAX_RUNTIME_SECONDS = 180.0


@dataclass(frozen=True)
class StoryboardShot:
    """One beat with a real shot cast into it."""

    number: int
    shot_code: str
    shot_name: str
    family: str
    frame: str
    lens: str
    camera_path: str
    lighting: str
    motion: str
    motivation: str
    intention: str
    continuity: str
    objective: str
    emotion: str
    duration_seconds: float

    def to_dict(self) -> dict[str, object]:
        return {
            "number": self.number,
            "shot_code": self.shot_code,
            "shot_name": self.shot_name,
            "family": self.family,
            "frame": self.frame,
            "lens": self.lens,
            "camera_path": self.camera_path,
            "lighting": self.lighting,
            "motion": self.motion,
            "motivation": self.motivation,
            "intention": self.intention,
            "continuity": self.continuity,
            "objective": self.objective,
            "emotion": self.emotion,
            "duration_seconds": self.duration_seconds,
        }


@dataclass(frozen=True)
class Storyboard:
    """A cast, ordered shot sequence."""

    brief: str
    format: str
    shots: tuple[StoryboardShot, ...]

    @property
    def scene_count(self) -> int:
        return len(self.shots)

    @property
    def runtime_seconds(self) -> float:
        return round(sum(shot.duration_seconds for shot in self.shots), 2)

    @property
    def lens_progression(self) -> tuple[str, ...]:
        return tuple(shot.lens for shot in self.shots)

    @property
    def family_sequence(self) -> tuple[str, ...]:
        return tuple(shot.family for shot in self.shots)

    @property
    def shot_codes(self) -> tuple[str, ...]:
        return tuple(shot.shot_code for shot in self.shots)

    def to_dict(self) -> dict[str, object]:
        return {
            "brief": self.brief,
            "format": self.format,
            "scene_count": self.scene_count,
            "runtime_seconds": self.runtime_seconds,
            "lens_progression": list(self.lens_progression),
            "family_sequence": list(self.family_sequence),
            "shot_codes": list(self.shot_codes),
            "shots": [shot.to_dict() for shot in self.shots],
        }


class StoryboardEngine:
    """Casts beats into shots and checks that the sequence holds together."""

    def __init__(
        self,
        director: DirectorAgent | None = None,
        shots: ShotLibrary | None = None,
        grammar: CinematicLibrary | None = None,
    ) -> None:
        self.director = director or DirectorAgent()
        self.shots = shots or ShotLibrary()
        self.grammar = grammar or CinematicLibrary()

    # -------------------------------------------------------------------- build

    def build(
        self,
        brief: str,
        *,
        scene_count: int = 5,
        persona: str | None = None,
        style: str | None = None,
        camera_language: str | None = None,
        duration_per_scene: float = 5.0,
    ) -> Storyboard:
        """Turn a brief into a cast storyboard.

        The Director supplies the beats (objective, emotion, duration) and the
        detected format; this engine supplies the shot for each beat. Nothing is
        invented here that the Director or the library does not already own.
        """

        beats = self.director.expand(
            brief,
            scene_count=scene_count,
            persona=persona,
            style=style,
            camera_language=camera_language,
            duration_per_scene=duration_per_scene,
        )
        return self.cast_beats(beats, brief=brief, format_name=self.director.detect_format(brief) or "film")

    def cast_beats(
        self,
        beats: tuple[SceneBeat, ...] | list[SceneBeat],
        *,
        brief: str = "",
        format_name: str = "film",
    ) -> Storyboard:
        """Cast an existing beat list. Useful when the Director already ran."""

        beats = tuple(beats)
        arc = self.arc_for(format_name, len(beats))
        cast: list[StoryboardShot] = []
        used: list[str] = []

        for beat, family in zip(beats, arc):
            shot = self._pick_shot(family, used=used)
            used.append(shot.code)
            motivations = self.grammar.motivation_of(shot.camera_path)
            cast.append(
                StoryboardShot(
                    number=beat.number,
                    shot_code=shot.code,
                    shot_name=shot.name,
                    family=shot.family or family,
                    frame=shot.frame,
                    lens=shot.lens,
                    camera_path=shot.camera_path,
                    lighting=shot.lighting,
                    motion=shot.speed,
                    motivation=", ".join(motivations) or "still",
                    intention=shot.intention,
                    continuity=shot.continuity,
                    objective=beat.objective,
                    emotion=beat.emotion,
                    duration_seconds=beat.duration_seconds,
                )
            )
        return Storyboard(brief=brief, format=format_name, shots=tuple(cast))

    # ---------------------------------------------------------------------- arc

    def arc_for(self, format_name: str, scene_count: int) -> tuple[str, ...]:
        """The family for each scene, for a given format and length.

        The canonical arc has five beats. A longer sequence repeats the middle
        development beat; a shorter one drops from the middle outwards, so the
        opening and the resolution always survive.
        """

        plan = ARC_BY_FORMAT.get(format_name, DEFAULT_ARC)
        count = max(MIN_SCENES, scene_count)
        if count == len(plan):
            return plan
        if count < len(plan):
            # Drop from the middle: keep the opening, the close, and as much of
            # the development as fits.
            keep_head = 1
            keep_tail = 1
            middle = list(plan[keep_head : len(plan) - keep_tail])
            need = count - keep_head - keep_tail
            trimmed = middle[:max(0, need)]
            return (plan[0], *trimmed, plan[-1])
        head, *middle, tail = plan
        repeats = count - len(plan)
        development = middle[len(middle) // 2] if middle else "action"
        return (head, *middle, *(development for _ in range(repeats)), tail)

    def formats(self) -> tuple[str, ...]:
        return tuple(ARC_BY_FORMAT)

    # ------------------------------------------------------------------- casting

    def _pick_shot(self, family: str, *, used: list[str]) -> ShotPreset:
        """Choose a shot from a family.

        Two rules: prefer a shot not yet used anywhere in the storyboard and,
        once the family is exhausted, reuse the one seen longest ago rather than
        the one just seen. Avoiding only the immediately previous shot is not
        enough — a 12-scene sequence would otherwise alternate between two
        shots, which passes a no-repeat-cut check and still reads as one shot
        twice.

        Casting is *not* emotion-aware on purpose. The Director emits four
        Portuguese emotions ("curiosidade", "desejo", "convicção", "tensão") and
        the library's intentions are English, so a token match finds nothing;
        a mapping between the two vocabularies belongs to the Director
        (ETAPA 7), not here. Verified before shipping: zero matches.
        """

        candidates = self.shots.by_family(family) or list(self.shots.all())
        fresh = [shot for shot in candidates if shot.code not in used]
        if fresh:
            return fresh[0]
        return min(candidates, key=lambda shot: used.index(shot.code))

    # --------------------------------------------------------------- validation

    def validate(self, storyboard: Storyboard) -> dict[str, object]:
        """Check that the sequence holds together.

        Returns a report rather than raising: a director needs to see *what* is
        wrong with a sequence, not just be told it failed.
        """

        findings: list[dict[str, str]] = []
        shots = storyboard.shots

        if storyboard.scene_count < MIN_SCENES:
            findings.append(
                {"rule": "scene-count", "status": "violation", "detail": f"a sequence needs at least {MIN_SCENES} scenes"}
            )

        for previous, current in zip(shots, shots[1:]):
            if previous.shot_code == current.shot_code:
                findings.append(
                    {
                        "rule": "no-repeat-cut",
                        "status": "violation",
                        "detail": f"scene {current.number} repeats {current.shot_code} from scene {previous.number}",
                    }
                )

        for shot in shots:
            if not self.grammar.motivation_of(shot.camera_path) and not self.grammar.is_still(shot.camera_path):
                findings.append(
                    {
                        "rule": "motion-motivated",
                        "status": "violation",
                        "detail": f"scene {shot.number} ({shot.shot_code}) movement names no motivation",
                    }
                )
            if self.grammar.focal_of(shot.lens) is None:
                findings.append(
                    {
                        "rule": "lens-declared",
                        "status": "attention",
                        "detail": f"scene {shot.number} ({shot.shot_code}) lens '{shot.lens}' is not declared",
                    }
                )
            if not shot.continuity:
                findings.append(
                    {
                        "rule": "continuity-declared",
                        "status": "attention",
                        "detail": f"scene {shot.number} ({shot.shot_code}) carries no continuity note",
                    }
                )

        if shots and shots[0].family != "establishing":
            findings.append(
                {
                    "rule": "arc-opens-establishing",
                    "status": "attention",
                    "detail": f"the sequence opens on '{shots[0].family}', not on geography",
                }
            )
        if shots and shots[-1].family != "resolution":
            findings.append(
                {
                    "rule": "arc-closes-resolution",
                    "status": "attention",
                    "detail": f"the sequence closes on '{shots[-1].family}', not on a resolution",
                }
            )

        if storyboard.runtime_seconds > MAX_RUNTIME_SECONDS:
            findings.append(
                {
                    "rule": "runtime",
                    "status": "violation",
                    "detail": f"{storyboard.runtime_seconds}s exceeds the {MAX_RUNTIME_SECONDS}s ceiling",
                }
            )

        return {
            "scene_count": storyboard.scene_count,
            "runtime_seconds": storyboard.runtime_seconds,
            "format": storyboard.format,
            "valid": not any(item["status"] == "violation" for item in findings),
            "violations": [item for item in findings if item["status"] == "violation"],
            "attention": [item for item in findings if item["status"] == "attention"],
        }

    # -------------------------------------------------------------- presentation

    def beat_sheet(self, storyboard: Storyboard) -> str:
        """A director-readable beat sheet. Direction, not a prompt."""

        lines = [
            f"{storyboard.format.upper()} — {storyboard.scene_count} scenes, {storyboard.runtime_seconds}s",
        ]
        for shot in storyboard.shots:
            lines.append(
                f"{shot.number:02d}. {shot.shot_code} {shot.shot_name} "
                f"[{shot.family}] {shot.lens} {shot.frame} — {shot.camera_path}; "
                f"{shot.lighting}. {shot.objective} ({shot.emotion})."
            )
        return "\n".join(lines)

    def as_beats(self, storyboard: Storyboard) -> tuple[SceneBeat, ...]:
        """Project the cast storyboard back onto `SceneBeat`.

        This is what lets the existing prompt path render a cast storyboard
        without any change to `PromptCompiler`: the beat now carries a real
        `shot_code` instead of `None`, plus the lens and the continuity note the
        cast shot brought with it. `PromptCompiler.compile_beats` consumes
        exactly this projection.
        """

        return tuple(
            SceneBeat(
                number=shot.number,
                objective=shot.objective,
                emotion=shot.emotion,
                camera=shot.camera_path,
                lighting=shot.lighting,
                motion=shot.motion,
                duration_seconds=shot.duration_seconds,
                shot_code=shot.shot_code,
                reference=shot.intention,
                lens=shot.lens,
                continuity=shot.continuity,
            )
            for shot in storyboard.shots
        )
