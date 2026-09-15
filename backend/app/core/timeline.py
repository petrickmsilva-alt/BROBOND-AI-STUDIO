"""VideoTimeline — the assembly of a directed storyboard into one cut.

The studio could direct a multi-scene sequence (ETAPA 8) and generate each scene
as its own job, but nothing ever put them back together: `FFmpegService` had a
single-source `export_h264` and no concatenation anywhere in the repository. A
five-scene storyboard produced five orphan files. `SYSTEM_PROMPT.md` asks the
Director to adjust "ritmo, lente, movimento, iluminação, **montagem**, som e
duração" — montagem was the one word with no code behind it.

What this component is: an **ordered assembly plan**. Clip order, in/out points,
transitions, the audio bed and the delivery geometry, with the total runtime
checked against the same ceiling the storyboard uses.

What it deliberately is NOT: a rendered file. A `Timeline` never claims media
exists. Clips whose source has not been produced yet are marked unrendered and
reported by `validate`, because `SYSTEM_PROMPT.md` forbids inventing outputs.

Responsibility boundaries, unchanged from the rest of the Core:
  * it does not compile prompt text (PromptCompiler);
  * it does not choose shots (StoryboardEngine);
  * it does not call FFmpeg (that is `app.media`, the application layer).

Independence: imports `contracts` only.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .contracts import DirectorIntent

#: Delivery aspect ratio per narrative format. A format is a *story* shape; this
#: is the frame it ships in. Reels and Stories are vertical because that is where
#: they are watched — the Director already says so in its own pacing language.
ASPECT_BY_FORMAT: dict[str, str] = {
    "reels": "9:16",
    "story": "9:16",
    "fashion": "16:9",
    "commercial": "16:9",
    "film": "16:9",
    "documentary": "16:9",
}

DEFAULT_ASPECT_RATIO = "16:9"

#: Delivery resolutions, matching `app.media.QUALITY` so a timeline and an
#: export agree on what "1080p" means.
RESOLUTIONS: dict[str, tuple[int, int]] = {
    "720p": (1280, 720),
    "1080p": (1920, 1080),
    "2k": (2560, 1440),
    "4k": (3840, 2160),
}

DEFAULT_RESOLUTION = "1080p"
DEFAULT_FPS = 24

#: Transition vocabulary. A hard cut is the default and needs no justification;
#: a dissolve is earned, and `VideoTimeline` only spends it where the storyboard
#: already says a shot bridges rather than carries.
CUT = "cut"
DISSOLVE = "dissolve"
TRANSITIONS: tuple[str, ...] = (CUT, DISSOLVE)

#: A cut shorter than this is a flash frame, not a shot.
MIN_CLIP_SECONDS = 0.5

#: Music fades, in seconds. Long enough to not click, short enough to not eat
#: the opening image.
DEFAULT_FADE_IN_SECONDS = 1.0
DEFAULT_FADE_OUT_SECONDS = 2.0


@dataclass(frozen=True)
class Clip:
    """One shot placed on the timeline.

    `source` is the rendered media for this clip — an object key or asset id.
    It is empty until that job has actually produced a file, and `Timeline`
    reports that honestly instead of pretending the cut is ready.
    """

    index: int
    shot_code: str
    family: str
    start_seconds: float
    duration_seconds: float
    transition: str = CUT
    source: str = ""

    @property
    def end_seconds(self) -> float:
        return round(self.start_seconds + self.duration_seconds, 3)

    @property
    def is_rendered(self) -> bool:
        return bool(self.source)

    def to_dict(self) -> dict[str, object]:
        return {
            "index": self.index,
            "shot_code": self.shot_code,
            "family": self.family,
            "start_seconds": self.start_seconds,
            "duration_seconds": self.duration_seconds,
            "end_seconds": self.end_seconds,
            "transition": self.transition,
            "source": self.source,
            "rendered": self.is_rendered,
        }


@dataclass(frozen=True)
class AudioTrack:
    """The music bed under the cut.

    `bed` is the Director's own music language ("percussão crescente com
    resolução quente"). This layer does not synthesise or fetch audio and does
    not pretend to: it carries the intent and the fades an editor needs.
    """

    bed: str = ""
    fade_in_seconds: float = DEFAULT_FADE_IN_SECONDS
    fade_out_seconds: float = DEFAULT_FADE_OUT_SECONDS

    @property
    def is_declared(self) -> bool:
        return bool(self.bed)

    def to_dict(self) -> dict[str, object]:
        return {
            "bed": self.bed,
            "fade_in_seconds": self.fade_in_seconds,
            "fade_out_seconds": self.fade_out_seconds,
            "declared": self.is_declared,
        }


@dataclass(frozen=True)
class Timeline:
    """An ordered cut: clips, audio, delivery geometry and total runtime."""

    format: str
    clips: tuple[Clip, ...]
    audio: AudioTrack = field(default_factory=AudioTrack)
    aspect_ratio: str = DEFAULT_ASPECT_RATIO
    resolution: str = DEFAULT_RESOLUTION
    fps: int = DEFAULT_FPS

    @property
    def clip_count(self) -> int:
        return len(self.clips)

    @property
    def duration_seconds(self) -> float:
        """Wall-clock length of the cut.

        Derived from the last clip's end point rather than summed from
        durations, so an overlap or a gap introduced by a caller is visible in
        the number instead of silently absorbed.
        """

        if not self.clips:
            return 0.0
        return round(max(clip.end_seconds for clip in self.clips), 3)

    @property
    def frame_size(self) -> tuple[int, int]:
        """Delivery box, swapped for a vertical aspect ratio."""

        width, height = RESOLUTIONS.get(self.resolution, RESOLUTIONS[DEFAULT_RESOLUTION])
        return (height, width) if self.aspect_ratio == "9:16" else (width, height)

    @property
    def width(self) -> int:
        return self.frame_size[0]

    @property
    def height(self) -> int:
        return self.frame_size[1]

    @property
    def rendered_clips(self) -> tuple[Clip, ...]:
        return tuple(clip for clip in self.clips if clip.is_rendered)

    @property
    def unrendered_clips(self) -> tuple[Clip, ...]:
        return tuple(clip for clip in self.clips if not clip.is_rendered)

    @property
    def is_complete(self) -> bool:
        """True only when every clip has real media behind it."""

        return bool(self.clips) and not self.unrendered_clips

    def to_dict(self) -> dict[str, object]:
        return {
            "format": self.format,
            "clip_count": self.clip_count,
            "duration_seconds": self.duration_seconds,
            "aspect_ratio": self.aspect_ratio,
            "resolution": self.resolution,
            "width": self.width,
            "height": self.height,
            "fps": self.fps,
            "complete": self.is_complete,
            "rendered_clips": len(self.rendered_clips),
            "unrendered_clips": [clip.index for clip in self.unrendered_clips],
            "audio": self.audio.to_dict(),
            "clips": [clip.to_dict() for clip in self.clips],
        }


class VideoTimeline:
    """Builds and checks assembly plans. Deterministic; no inference."""

    def __init__(self, *, max_runtime_seconds: float = 180.0) -> None:
        #: Same ceiling the StoryboardEngine enforces, so a sequence that passed
        #: there cannot fail here for a different reason.
        self.max_runtime_seconds = max_runtime_seconds

    # ------------------------------------------------------------------ public

    def aspect_for(self, format_name: str) -> str:
        return ASPECT_BY_FORMAT.get(format_name, DEFAULT_ASPECT_RATIO)

    def transition_for(self, family: str, previous_family: str | None) -> str:
        """Dissolve inside one idea, cut between two.

        Two consecutive shots from the same family are a continuation — the
        subject has not changed, so a hard cut reads as a jump. A change of
        family is a change of idea and takes the cut.

        The first clip always cuts: there is nothing to come from.

        Note on what this is *not*: `StoryboardEngine.TRANSITION_FAMILIES`
        ("transition", "atmosphere") looks like the obvious trigger, and the
        first draft used it. It is dead — no arc in `ARC_BY_FORMAT` ever casts
        those families, so the intersection is empty and a dissolve could never
        have been emitted. Verified before shipping the rule below.
        """

        if previous_family is None:
            return CUT
        return DISSOLVE if (family and family == previous_family) else CUT

    def assemble(
        self,
        shots: tuple[object, ...] | list[object],
        *,
        format_name: str,
        music: str = "",
        sources: dict[int, str] | None = None,
        resolution: str = DEFAULT_RESOLUTION,
        fps: int = DEFAULT_FPS,
        fade_in_seconds: float = DEFAULT_FADE_IN_SECONDS,
        fade_out_seconds: float = DEFAULT_FADE_OUT_SECONDS,
    ) -> Timeline:
        """Lay shots end to end and return the resulting cut.

        `shots` are `StoryboardShot` objects (or anything exposing `shot_code`,
        `family` and `duration_seconds`). `sources` maps a 1-based shot number to
        the media already rendered for it; shots absent from it stay unrendered,
        which `validate` then reports.
        """

        resolved = sources or {}
        clips: list[Clip] = []
        cursor = 0.0
        previous_family: str | None = None
        for position, shot in enumerate(shots):
            duration = max(float(getattr(shot, "duration_seconds", 0.0) or 0.0), 0.0)
            family = str(getattr(shot, "family", "") or "")
            number = int(getattr(shot, "number", position + 1))
            clips.append(
                Clip(
                    index=position + 1,
                    shot_code=str(getattr(shot, "shot_code", "") or ""),
                    family=family,
                    start_seconds=round(cursor, 3),
                    duration_seconds=round(duration, 3),
                    transition=self.transition_for(family, previous_family),
                    source=str(resolved.get(number, "") or ""),
                )
            )
            cursor += duration
            previous_family = family

        return Timeline(
            format=format_name,
            clips=tuple(clips),
            audio=AudioTrack(
                bed=music,
                fade_in_seconds=fade_in_seconds,
                fade_out_seconds=fade_out_seconds,
            ),
            aspect_ratio=self.aspect_for(format_name),
            resolution=resolution,
            fps=fps,
        )

    def from_storyboard(
        self,
        storyboard: object,
        *,
        intent: DirectorIntent | None = None,
        sources: dict[int, str] | None = None,
        resolution: str = DEFAULT_RESOLUTION,
        fps: int = DEFAULT_FPS,
    ) -> Timeline:
        """Assemble straight from a Storyboard, taking music from the Director.

        The audio bed is the Director's own music language rather than a file:
        nothing here invents a soundtrack that does not exist.
        """

        return self.assemble(
            getattr(storyboard, "shots", ()),
            format_name=str(getattr(storyboard, "format", "") or ""),
            music=str(getattr(intent, "music", "") or "") if intent else "",
            sources=sources,
            resolution=resolution,
            fps=fps,
        )

    # -------------------------------------------------------------- validation

    def validate(self, timeline: Timeline) -> dict[str, object]:
        """Report what is wrong with a cut instead of raising.

        Mirrors `StoryboardEngine.validate`: a director needs to see the finding,
        not be told it failed. Unrendered clips are a finding, never a crash and
        never a silent pass.
        """

        findings: list[dict[str, str]] = []

        if timeline.clip_count == 0:
            findings.append(
                {
                    "rule": "empty-timeline",
                    "status": "violation",
                    "detail": "a timeline needs at least one clip",
                }
            )

        if timeline.duration_seconds > self.max_runtime_seconds:
            findings.append(
                {
                    "rule": "runtime",
                    "status": "violation",
                    "detail": f"{timeline.duration_seconds}s exceeds the {self.max_runtime_seconds}s ceiling",
                }
            )

        for clip in timeline.clips:
            if clip.duration_seconds < MIN_CLIP_SECONDS:
                findings.append(
                    {
                        "rule": "clip-duration",
                        "status": "violation",
                        "detail": f"clip {clip.index} runs {clip.duration_seconds}s, below the {MIN_CLIP_SECONDS}s floor",
                    }
                )

        for previous, current in zip(timeline.clips, timeline.clips[1:]):
            if current.start_seconds < previous.end_seconds - 1e-6:
                findings.append(
                    {
                        "rule": "overlap",
                        "status": "violation",
                        "detail": f"clip {current.index} starts at {current.start_seconds}s, before clip {previous.index} ends at {previous.end_seconds}s",
                    }
                )
            elif current.start_seconds > previous.end_seconds + 1e-6:
                findings.append(
                    {
                        "rule": "gap",
                        "status": "warning",
                        "detail": f"{round(current.start_seconds - previous.end_seconds, 3)}s of black between clips {previous.index} and {current.index}",
                    }
                )

        for clip in timeline.unrendered_clips:
            findings.append(
                {
                    "rule": "unrendered-clip",
                    "status": "warning",
                    "detail": f"clip {clip.index} ({clip.shot_code or 'no shot'}) has no rendered media yet",
                }
            )

        if not timeline.audio.is_declared:
            findings.append(
                {
                    "rule": "no-audio-bed",
                    "status": "warning",
                    "detail": "the Director declared no music for this cut",
                }
            )

        if timeline.audio.is_declared:
            if timeline.audio.fade_out_seconds > timeline.duration_seconds:
                findings.append(
                    {
                        "rule": "audio-fade",
                        "status": "violation",
                        "detail": f"the {timeline.audio.fade_out_seconds}s fade outlasts a {timeline.duration_seconds}s cut",
                    }
                )

        if timeline.resolution not in RESOLUTIONS:
            findings.append(
                {
                    "rule": "resolution",
                    "status": "violation",
                    "detail": f"unknown resolution {timeline.resolution!r}; expected one of {sorted(RESOLUTIONS)}",
                }
            )

        return {
            "valid": not any(f["status"] == "violation" for f in findings),
            "violations": [f for f in findings if f["status"] == "violation"],
            "warnings": [f for f in findings if f["status"] == "warning"],
            "duration_seconds": timeline.duration_seconds,
            "rendered": len(timeline.rendered_clips),
            "unrendered": len(timeline.unrendered_clips),
        }
