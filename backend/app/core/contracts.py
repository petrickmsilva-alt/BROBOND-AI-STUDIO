"""BROBOND CORE contracts — re-export façade over `app.contracts`.

Vocabulary only: frozen dataclasses, enums and protocols. This module imports
nothing from the rest of the package, which is what allows every Core component
(`MemoryResolver`, `StyleResolver`, `ShotResolver`, `PromptCompiler`,
`DirectorAgent`, `GenerationSpecBuilder`) to be imported, instantiated and
tested on its own.

Rule enforced here: a contract never decides anything. Behaviour lives in the
component that owns that vocabulary.

PR010.0 — where the definitions actually live
---------------------------------------------
ETAPA 4 of the Platform Freeze moved these declarations into
`backend/app/contracts/`, so the shared vocabulary is owned by one package
instead of by the Core. This module stays, exporting the same objects, because
the standing rule is that an existing import path never breaks (Bible §2):
twenty modules and a large part of the suite import `app.core.contracts`, and
all of them keep working unchanged.

There is no duplication and no copy. These are re-exports, so identity holds::

    from app.core.contracts import GenerationSpec as A
    from app.contracts import GenerationSpec as B
    A is B  # True

`backend/tests/test_architecture_boundaries.py` asserts that identity for every
name below, and fails if anything in the tree defines a second version of a
contract. New code should import from `app.contracts`; this façade is kept for
the callers that predate the freeze.
"""
from __future__ import annotations

from ..contracts import (
    GENERATION_SPEC_FIELDS,
    NEGATIVE_BLOCK,
    PERSONA_IDENTITY_FIELDS,
    PROMPT_BLOCK_ORDER,
    PROMPT_BLOCKS,
    SPEC_SCHEMA_VERSION,
    CompiledPrompt,
    DirectorIntent,
    GenerationKind,
    GenerationSpec,
    GraphContext,
    GraphContextSource,
    LanguageModel,
    PersonaMemory,
    PersonaProfile,
    PersonaProfileSource,
    PersonaSource,
    PersonaStatus,
    PromptBlocks,
    ReferenceImage,
    SceneBeat,
    ShotPreset,
    ShotSource,
    StylePreset,
    StyleSource,
    WardrobeItem,
)

__all__ = [
    "GENERATION_SPEC_FIELDS",
    "NEGATIVE_BLOCK",
    "PERSONA_IDENTITY_FIELDS",
    "PROMPT_BLOCKS",
    "PROMPT_BLOCK_ORDER",
    "SPEC_SCHEMA_VERSION",
    "CompiledPrompt",
    "DirectorIntent",
    "GenerationKind",
    "GenerationSpec",
    "GraphContext",
    "GraphContextSource",
    "LanguageModel",
    "PersonaMemory",
    "PersonaProfile",
    "PersonaProfileSource",
    "PersonaSource",
    "PersonaStatus",
    "PromptBlocks",
    "ReferenceImage",
    "SceneBeat",
    "ShotPreset",
    "ShotSource",
    "StylePreset",
    "StyleSource",
    "WardrobeItem",
]
