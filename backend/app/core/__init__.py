"""Core configuration and infrastructure primitives.

BROBOND CORE — the decision layer.

Thirteen top-level components live here; eight of them import only `contracts`. PR005 adds the
`core.director` package for production planning and PR006 storyboard editing without changing those legacy boundaries:

    MemoryResolver          permanent character identity + versioning
    StyleResolver           the cinematic library (style -> full vocabulary)
    ShotResolver            the shot library (stable codes -> direction preset)
    PromptCompiler          the only place prompt text is produced
    DirectorAgent           plain-language intention -> direction
    PersonaMemoryEngine     versioned, governed persona memory (ETAPA 4)
    CinematicLibrary        the Bible's grammar + the rules that enforce it (ETAPA 5)
    ShotLibrary             the 300-shot library + its Bible compliance (ETAPA 6)
    StoryboardEngine        casts beats into shots, chains and validates (ETAPA 8)
    VideoTimeline           assembles a storyboard into one cut (ETAPA 13)
    QualityGate             structural assessment of a rendered artifact (ETAPA 14)
    GenerationSpecBuilder   the composition root -> GenerationSpec
    JobService              job lifecycle state machine over a JobRepository (PR004-prep)

    core.director           PR005 ProductionPlan, ShotPlan, MoodEngine,
                            CameraDirector and DirectorAgent (planning only);
                            PR006 StoryboardState and StoryboardHistory
                            (plan editing only)

Wiring lives at the application boundary (`app.main`), never between the
components: GenerationSpecBuilder receives the other four by injection.
"""
from .cinematic_library import (
    ANGLES,
    FRAMES,
    LENSES,
    LIGHTS,
    MOTIVATIONS,
    TIME_QUALITIES,
    AngleProfile,
    CinematicLibrary,
    FrameProfile,
    LensProfile,
    LightingProfile,
    Motivation,
    RuleFinding,
    TimeQuality,
)
from .contracts import (
    GENERATION_SPEC_FIELDS,
    PROMPT_BLOCK_ORDER,
    SPEC_SCHEMA_VERSION,
    CompiledPrompt,
    DirectorIntent,
    GenerationKind,
    GenerationSpec,
    LanguageModel,
    PersonaMemory,
    PersonaSource,
    PersonaStatus,
    PromptBlocks,
    SceneBeat,
    ShotPreset,
    ShotSource,
    StylePreset,
    StyleSource,
)
from .director_agent import DirectorAgent
from .generation_spec_builder import BuildResult, GenerationSpecBuilder, ResolutionTrace
from .job_service import InvalidJobTransition, JOB_STATUSES, JOB_TERMINAL_STATUSES, JOB_TRANSITIONS, Job, JobService
from .memory_resolver import MemoryError_, MemoryResolver, SeedPersonaSource
from .persona_memory import (
    IDENTITY_DEFINITION_FIELDS,
    PersonaLedger,
    PersonaMemoryEngine,
    PersonaNotFound,
    PersonaVersion,
)
from .prompt_compiler import PromptCompiler, PromptCompilerError
from .quality import (
    ASPECT_RATIOS,
    ASPECT_TOLERANCE,
    FAIL,
    MIN_SIDE_PIXELS,
    PASS,
    VERDICTS,
    WARN,
    MeasuredOutput,
    QualityGate,
    QualityReport,
)
from .shot_library import (
    EXPANDED_SHOTS,
    FAMILIES,
    FAMILY_LABELS,
    FULL_SHOT_LIBRARY,
    LIBRARY_TARGET,
    PUBLISHED_CODES,
    ShotLibrary,
)
from .shot_resolver import SeedShotSource, ShotResolver
from .storyboard_engine import (
    ARC_BY_FORMAT,
    DEFAULT_ARC,
    MAX_RUNTIME_SECONDS,
    MIN_SCENES,
    Storyboard,
    StoryboardEngine,
    StoryboardShot,
)
from .style_resolver import SeedStyleSource, StyleResolver
from .timeline import (
    ASPECT_BY_FORMAT,
    CUT,
    DEFAULT_ASPECT_RATIO,
    DEFAULT_FPS,
    DEFAULT_RESOLUTION,
    DISSOLVE,
    RESOLUTIONS,
    TRANSITIONS,
    AudioTrack,
    Clip,
    Timeline,
    VideoTimeline,
)
from .director import (
    CameraDirection,
    CameraDirector,
    DirectorAgent as ProductionDirectorAgent,
    MoodEngine,
    MoodPreset,
    ProductionPlan,
    ShotPlan,
    StoryboardHistory,
    StoryboardScene,
    StoryboardState,
)

__all__ = [
    "ANGLES",
    "ASPECT_RATIOS",
    "ASPECT_TOLERANCE",
    "ASPECT_BY_FORMAT",
    "ARC_BY_FORMAT",
    "AngleProfile",
    "AudioTrack",
    "BuildResult",
    "CUT",
    "CameraDirection",
    "CameraDirector",
    "CinematicLibrary",
    "Clip",
    "CompiledPrompt",
    "DEFAULT_ARC",
    "DEFAULT_ASPECT_RATIO",
    "DEFAULT_FPS",
    "DEFAULT_RESOLUTION",
    "DISSOLVE",
    "DirectorAgent",
    "DirectorIntent",
    "EXPANDED_SHOTS",
    "FAMILIES",
    "FAMILY_LABELS",
    "FRAMES",
    "FULL_SHOT_LIBRARY",
    "FAIL",
    "FrameProfile",
    "GENERATION_SPEC_FIELDS",
    "GenerationKind",
    "GenerationSpec",
    "GenerationSpecBuilder",
    "InvalidJobTransition",
    "JOB_STATUSES",
    "JOB_TERMINAL_STATUSES",
    "JOB_TRANSITIONS",
    "Job",
    "JobService",
    "VideoTimeline",
    "WARN",
    "IDENTITY_DEFINITION_FIELDS",
    "LENSES",
    "LIBRARY_TARGET",
    "LIGHTS",
    "LanguageModel",
    "LensProfile",
    "LightingProfile",
    "MAX_RUNTIME_SECONDS",
    "MIN_SCENES",
    "MIN_SIDE_PIXELS",
    "MeasuredOutput",
    "MOTIVATIONS",
    "MemoryError_",
    "MemoryResolver",
    "MoodEngine",
    "MoodPreset",
    "Motivation",
    "PROMPT_BLOCK_ORDER",
    "PUBLISHED_CODES",
    "PASS",
    "ProductionDirectorAgent",
    "ProductionPlan",
    "QualityGate",
    "QualityReport",
    "PersonaLedger",
    "PersonaMemory",
    "PersonaMemoryEngine",
    "PersonaNotFound",
    "PersonaSource",
    "PersonaStatus",
    "PersonaVersion",
    "PromptBlocks",
    "PromptCompiler",
    "PromptCompilerError",
    "RESOLUTIONS",
    "ResolutionTrace",
    "RuleFinding",
    "SPEC_SCHEMA_VERSION",
    "SceneBeat",
    "SeedPersonaSource",
    "SeedShotSource",
    "SeedStyleSource",
    "ShotLibrary",
    "ShotPlan",
    "ShotPreset",
    "ShotResolver",
    "StoryboardHistory",
    "StoryboardScene",
    "StoryboardState",
    "ShotSource",
    "Storyboard",
    "StoryboardEngine",
    "StoryboardShot",
    "StylePreset",
    "StyleResolver",
    "StyleSource",
    "TIME_QUALITIES",
    "VERDICTS",
    "TRANSITIONS",
    "Timeline",
    "TimeQuality",
]
