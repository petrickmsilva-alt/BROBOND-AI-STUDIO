"""Director AI Engine — human intent to immutable production plan."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from ..contracts import PromptBlocks
from ..prompt_compiler import PromptCompiler
from .camera_director import CameraDirector, CameraDirection
from .mood_config import MoodPreset
from .mood_engine import MoodEngine
from .production_plan import ProductionPlan
from .shot_plan import FIRST_SCENE_NUMBER, ShotPlan

MIN_STORYBOARD_SCENES = 4
MAX_STORYBOARD_SCENES = 8
SHORT_DURATION_SECONDS = 15
MEDIUM_DURATION_SECONDS = 30
EXTENDED_DURATION_SECONDS = 45
LONG_DURATION_SECONDS = 75
DEFAULT_DURATION_SECONDS = 30
DURATION_PRECISION_DIGITS = 4

DURATION_TIERS: tuple[tuple[float, int], ...] = (
    (SHORT_DURATION_SECONDS, MIN_STORYBOARD_SCENES),
    (MEDIUM_DURATION_SECONDS, MIN_STORYBOARD_SCENES + 1),
    (EXTENDED_DURATION_SECONDS, MIN_STORYBOARD_SCENES + 2),
    (LONG_DURATION_SECONDS, MIN_STORYBOARD_SCENES + 3),
)

DURATION_WEIGHTS: tuple[float, ...] = (
    1.00,
    0.85,
    1.20,
    0.95,
    1.35,
    0.75,
    1.10,
    0.90,
)

TITLE_WORD_LIMIT = 7
EMPTY_INTENT_TITLE = "Untitled Production"
DEFAULT_PLATFORM = "studio"
DEFAULT_PERSONA_VOICE = "natural confident narration"
NEGATIVE_QUALITY_GUARD = "no random cuts, no incoherent geography, no unmotivated camera movement"
CONTINUITY_LINE = "same protagonist, product identity, color grade and spatial logic across the sequence"

_WORD_PATTERN = re.compile(r"[a-zà-öø-ÿ0-9]+", re.IGNORECASE)
_SPACE_PATTERN = re.compile(r"\s+")

PLATFORM_AUDIENCES: dict[str, str] = {
    "instagram": "mobile-first social audience that decides fast",
    "reels": "vertical social audience watching with rapid thumb-stops",
    "tiktok": "short-form audience that needs an instant visual hook",
    "youtube": "creator-led audience with room for story and payoff",
    "ads": "conversion-focused audience evaluating value quickly",
    "cinema": "cinematic audience expecting atmosphere, scale and payoff",
    "web": "brand-site audience looking for clarity and polish",
    DEFAULT_PLATFORM: "general studio audience seeking a complete cinematic idea",
}

MUSIC_BY_MOOD: dict[str, str] = {
    "Luxury": "minimal premium pulse, soft sub-bass and polished accents",
    "Epic": "orchestral rise, percussion swell and final impact",
    "Dark": "low analog drone, sparse hits and negative space",
    "Minimal": "restrained ambient bed with clean tonal movement",
    "Sport": "kinetic percussion, breath rhythm and impact hits",
    "Neo": "synthetic pulse, neon pads and tight electronic cuts",
}

VOICE_BY_MOOD: dict[str, str] = {
    "Luxury": "calm, assured, premium voice with restrained emotion",
    "Epic": "commanding voice with scale and forward momentum",
    "Dark": "low intimate voice, controlled and tense",
    "Minimal": DEFAULT_PERSONA_VOICE,
    "Sport": "direct motivational voice with breath and discipline",
    "Neo": "sleek contemporary voice with precise rhythm",
}


@dataclass(frozen=True)
class StoryBeatTemplate:
    title: str
    objective: str
    emotion: str
    action: str
    environment: str


STORY_BEATS: tuple[StoryBeatTemplate, ...] = (
    StoryBeatTemplate(
        title="Abertura do Mundo",
        objective="Apresentar o universo e o desejo central antes de qualquer detalhe técnico.",
        emotion="curiosidade",
        action="O mundo aparece primeiro; a presença principal entra como promessa, não como explicação.",
        environment="wide environment that reveals scale, texture and atmosphere",
    ),
    StoryBeatTemplate(
        title="Primeiro Sinal",
        objective="Mostrar por que a ideia merece atenção visual e emocional.",
        emotion="atração",
        action="Um gesto, material ou rosto captura a atenção e transforma a ideia em objeto de desejo.",
        environment="controlled foreground detail inside the established world",
    ),
    StoryBeatTemplate(
        title="Movimento de Prova",
        objective="Provar valor por ação, textura ou performance, sem narração explicativa.",
        emotion="confiança",
        action="A cena deixa o valor ser visto em uso: movimento real, reação real, consequência clara.",
        environment="practical path through the core environment with readable geography",
    ),
    StoryBeatTemplate(
        title="Virada Emocional",
        objective="Criar a mudança interna que justifica a progressão da história.",
        emotion="tensão",
        action="A imagem pausa no instante em que algo muda: decisão, risco, reconhecimento ou desejo.",
        environment="compressed emotional space with motivated light and visible stakes",
    ),
    StoryBeatTemplate(
        title="Ritual e Detalhe",
        objective="Aprofundar o que torna a produção específica e memorável.",
        emotion="intimidade",
        action="Detalhes ganham tempo: mão, material, respiração, mecanismo ou preparação revelam cuidado.",
        environment="tactile detail environment connected to the hero object or persona",
    ),
    StoryBeatTemplate(
        title="Escala Revelada",
        objective="Abrir a narrativa para mostrar consequência, alcance ou transformação.",
        emotion="expansão",
        action="A câmera revela que a decisão afetou o espaço; o mundo responde ao protagonista ou produto.",
        environment="expanded environment that pays off the geography introduced earlier",
    ),
    StoryBeatTemplate(
        title="Escolha Final",
        objective="Concentrar a história num gesto final editável pelo usuário depois.",
        emotion="convicção",
        action="Um gesto resolve a intenção: vestir, acelerar, assinar, encarar, lançar ou atravessar.",
        environment="clean decision space with no visual noise around the final action",
    ),
    StoryBeatTemplate(
        title="Imagem que Fica",
        objective="Encerrar com uma imagem de memória, não com explicação.",
        emotion="reverência",
        action="A última composição sustenta o resultado e deixa a audiência completar o significado.",
        environment="final frame environment preserving the same light logic and palette",
    ),
)


class DirectorAgent:
    """Transforms language into a complete, immutable cinematic production plan."""

    def __init__(
        self,
        *,
        mood_engine: MoodEngine | None = None,
        camera_director: CameraDirector | None = None,
        prompt_compiler: PromptCompiler | None = None,
    ) -> None:
        self._mood_engine = mood_engine or MoodEngine()
        self._camera_director = camera_director or CameraDirector()
        self._prompt_compiler = prompt_compiler or PromptCompiler()

    def create_production_plan(
        self,
        user_intent: str,
        persona_id: str | None,
        platform: str,
        duration: float | None,
        *,
        mood: str | None = None,
    ) -> ProductionPlan:
        """Create the PR005 planning artifact without rendering anything.

        Flow: Intent -> Mood -> Style -> Shot Sequence -> Storyboard -> Prompt
        Compiler -> ProductionPlan. Providers are never imported or called.
        """

        cleaned_intent = self._clean_intent(user_intent)
        normalized_platform = self._platform(platform)
        planned_duration = self._duration(duration)
        mood_preset = self._mood_engine.resolve(mood, user_intent=cleaned_intent)
        style = self._style_for(mood_preset)
        scene_count = self._scene_count_for_duration(planned_duration)
        durations = self._durations(planned_duration, scene_count)
        beats = self._storyboard(cleaned_intent, scene_count)

        shots: list[ShotPlan] = []
        for offset, template in enumerate(beats):
            scene_number = FIRST_SCENE_NUMBER + offset
            camera = self._camera_director.choose(
                scene_number=scene_number,
                scene_count=scene_count,
                objective=template.objective,
                emotion=template.emotion,
                mood=mood_preset.name,
                platform=normalized_platform,
            )
            shot = self._compile_shot(
                scene_number=scene_number,
                template=template,
                intent=cleaned_intent,
                persona_id=persona_id,
                platform=normalized_platform,
                duration=durations[offset],
                mood_name=mood_preset.name,
                style=style,
                camera=camera,
            )
            shots.append(shot)

        return ProductionPlan(
            id=f"prod_{uuid4().hex}",
            title=self._title(cleaned_intent),
            concept=self._concept(cleaned_intent, mood_preset.name, normalized_platform),
            mood=mood_preset.name,
            audience=PLATFORM_AUDIENCES.get(normalized_platform, PLATFORM_AUDIENCES[DEFAULT_PLATFORM]),
            platform=normalized_platform,
            duration=planned_duration,
            style=style,
            music=MUSIC_BY_MOOD[mood_preset.name],
            voice=VOICE_BY_MOOD[mood_preset.name],
            persona_id=persona_id or None,
            shots=tuple(shots),
            created_at=datetime.now(UTC),
        )

    def _compile_shot(
        self,
        *,
        scene_number: int,
        template: StoryBeatTemplate,
        intent: str,
        persona_id: str | None,
        platform: str,
        duration: float,
        mood_name: str,
        style: str,
        camera: CameraDirection,
    ) -> ShotPlan:
        environment = self._environment(template, platform=platform, mood_name=mood_name)
        compiled = self._prompt_compiler.compile(
            PromptBlocks(
                subject=intent,
                persona=self._persona_phrase(persona_id),
                environment=environment,
                action=template.action,
                camera=camera.camera,
                lens=camera.lens,
                light=camera.lighting,
                color=style,
                motion=camera.motion,
                style=style,
                continuity=CONTINUITY_LINE,
                output=self._prompt_compiler.output_block,
                negative=NEGATIVE_QUALITY_GUARD,
            )
        )
        return ShotPlan(
            scene_number=scene_number,
            title=template.title,
            objective=template.objective,
            emotion=template.emotion,
            camera=camera.camera,
            lens=camera.lens,
            lighting=camera.lighting,
            motion=camera.motion,
            duration=duration,
            prompt=compiled.prompt,
            negative_prompt=compiled.negative_prompt,
            environment=environment,
        )

    def _storyboard(self, intent: str, scene_count: int) -> tuple[StoryBeatTemplate, ...]:
        return tuple(
            StoryBeatTemplate(
                title=template.title,
                objective=template.objective,
                emotion=template.emotion,
                action=f"{template.action} Intenção central: {intent.strip().rstrip('.')}",
                environment=template.environment,
            )
            for template in STORY_BEATS[:scene_count]
        )

    @staticmethod
    def _clean_intent(user_intent: str) -> str:
        cleaned = _SPACE_PATTERN.sub(" ", (user_intent or "").strip())
        if not cleaned:
            raise ValueError("user_intent is required")
        return cleaned

    @staticmethod
    def _platform(platform: str) -> str:
        normalized = (platform or DEFAULT_PLATFORM).strip().casefold()
        return normalized or DEFAULT_PLATFORM

    @staticmethod
    def _duration(duration: float | None) -> float:
        value = DEFAULT_DURATION_SECONDS if duration is None else float(duration)
        if value <= 0:
            raise ValueError("duration must be positive")
        return value

    @staticmethod
    def _scene_count_for_duration(duration: float) -> int:
        for ceiling, scenes in DURATION_TIERS:
            if duration <= ceiling:
                return scenes
        return MAX_STORYBOARD_SCENES

    @staticmethod
    def _durations(total_duration: float, scene_count: int) -> tuple[float, ...]:
        weights = DURATION_WEIGHTS[:scene_count]
        weight_sum = sum(weights)
        durations = [round(total_duration * weight / weight_sum, DURATION_PRECISION_DIGITS) for weight in weights]
        durations[-1] = round(total_duration - sum(durations[:-1]), DURATION_PRECISION_DIGITS)
        return tuple(durations)

    @staticmethod
    def _title(intent: str) -> str:
        words = _WORD_PATTERN.findall(intent)
        if not words:
            return EMPTY_INTENT_TITLE
        title = " ".join(words[:TITLE_WORD_LIMIT])
        return title[:1].upper() + title[1:]

    @staticmethod
    def _concept(intent: str, mood_name: str, platform: str) -> str:
        return f"{mood_name} cinematic production for {platform}: {intent.strip().rstrip('.')}"

    def _style_for(self, mood_preset: MoodPreset) -> str:
        return self._mood_engine.describe(mood_preset)

    @staticmethod
    def _persona_phrase(persona_id: str | None) -> str:
        return f"persona memory {persona_id}" if persona_id else "no locked persona"

    @staticmethod
    def _environment(template: StoryBeatTemplate, *, platform: str, mood_name: str) -> str:
        return f"{template.environment}; planned for {platform}; {mood_name} mood continuity"
