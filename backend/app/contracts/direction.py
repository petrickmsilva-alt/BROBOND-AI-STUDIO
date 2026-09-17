"""Direction contracts — what the Director decides.

A beat carries narrative intent and camera language, never compiled prompt
text: the Director owns meaning, the PromptCompiler owns words. The
`LanguageModel` protocol is the optional LLM hook — with nothing injected
the Director stays deterministic and says so.

PR010.0 froze this vocabulary. It was moved here verbatim from
`app/core/contracts.py`, which now re-exports it: the objects are the *same*
objects, so `app.core.contracts.SceneBeat is app.contracts.SceneBeat`. A module
that needs this vocabulary imports it; it never restates it.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Protocol, runtime_checkable

@dataclass(frozen=True)
class SceneBeat:
    """One directed scene, produced by the DirectorAgent.

    Carries narrative intent and camera language, never a compiled prompt: the
    PromptCompiler owns text, the Director owns meaning.
    """

    number: int
    objective: str
    emotion: str
    camera: str
    lighting: str
    motion: str
    duration_seconds: float = 5.0
    shot_code: str | None = None
    reference: str = ""
    #: Filled by StoryboardEngine.as_beats when the beat has a shot cast into
    #: it (ETAPA 9). Empty for an uncast beat, so the Director's own beats are
    #: unaffected and the prompt simply omits the block.
    lens: str = ""
    continuity: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

@dataclass(frozen=True)
class DirectorIntent:
    """The Director's answer to a plain-language request.

    This is the object a user-facing conversation ends with: concept, script,
    scenes, cameras, music and duration. No technical prompt is ever exposed.
    """

    intent: str
    concept: str
    format: str
    logline: str
    script: str
    beats: tuple[SceneBeat, ...]
    camera_language: str
    lighting_language: str
    music: str
    pacing: str
    style_hint: str
    duration_seconds: float
    #: Short direction question, filled only when the intention could follow
    #: more than one language. SYSTEM_PROMPT.md: "faça uma pergunta curta de
    #: direção". Empty means the director is confident.
    clarification: str = ""

    @property
    def scene_count(self) -> int:
        return len(self.beats)

    @property
    def needs_direction(self) -> bool:
        return bool(self.clarification)

    def to_dict(self) -> dict[str, object]:
        return {
            "intent": self.intent,
            "concept": self.concept,
            "format": self.format,
            "logline": self.logline,
            "script": self.script,
            "beats": [beat.to_dict() for beat in self.beats],
            "camera_language": self.camera_language,
            "lighting_language": self.lighting_language,
            "music": self.music,
            "pacing": self.pacing,
            "style_hint": self.style_hint,
            "duration_seconds": self.duration_seconds,
            "scene_count": self.scene_count,
            "clarification": self.clarification,
        }

@runtime_checkable
class LanguageModel(Protocol):
    """Optional LLM hook for the DirectorAgent.

    Nothing in the Core pretends a model is loaded: when no implementation is
    injected the Director stays deterministic and says so.
    """

    def complete(self, instruction: str, context: str) -> str:
        ...
