"""BROBOND domain contracts — the only language modules speak to each other.

PR010.0 (Platform Freeze), ETAPA 4. This package is the **single** home of the
shared public vocabulary: frozen dataclasses, enums and protocols. It imports
nothing from the rest of the application, which is what lets any module depend
on it without inheriting that module's dependencies.

Where it came from
------------------
The vocabulary was born in `app/core/contracts.py` (ETAPA 2) and grew there
through ETAPA 3, PR003, V3.1 and PR009. PR010.0 moved the definitions here
**verbatim** and turned the old module into a re-export façade, the same way
`lib/projectMemory.ts` delegates to `lib/memory/project_memory.ts`. The objects
are shared, not copied::

    app.core.contracts.GenerationSpec is app.contracts.GenerationSpec  # True

So every import written before this PR keeps working, byte for byte, and there
is still exactly one definition of each contract. `test_architecture_boundaries.py`
asserts both halves of that sentence.

The two rules this package exists to enforce
--------------------------------------------
1. **A contract never decides anything.** Behaviour lives in the module that
   owns the vocabulary. These types carry data and shape; they do not branch on
   business rules, reach for a database or produce prompt text.
2. **No module may restate a contract.** If two modules need to agree on a
   shape, the shape lives here. A duplicate definition elsewhere is a fork of
   the contract that will drift, and the boundary guard fails on it.

Layout
------
=======================  ====================================================
`generation.py`          `GenerationSpec` and the mandatory field list — what
                         a provider receives, and nothing else.
`prompt.py`              The thirteen prompt blocks and the compiled result.
`persona.py`             Permanent, versioned character identity + sources.
`cinematic.py`           Style presets, shot presets and their sources.
`direction.py`           Scene beats, director intent, the LLM hook.
`graph.py`               Knowledge Graph context for one subject.
=======================  ====================================================

Adding a contract means adding it to one of those files and to `__all__` here.
Nothing else in the tree may define it.
"""
from __future__ import annotations

from .cinematic import ShotPreset, ShotSource, StylePreset, StyleSource
from .direction import DirectorIntent, LanguageModel, SceneBeat
from .generation import (
    GENERATION_SPEC_FIELDS,
    SPEC_SCHEMA_VERSION,
    GenerationKind,
    GenerationSpec,
)
from .graph import GraphContext, GraphContextSource
from .persona import (
    PERSONA_IDENTITY_FIELDS,
    PersonaMemory,
    PersonaProfile,
    PersonaProfileSource,
    PersonaSource,
    PersonaStatus,
    ReferenceImage,
    WardrobeItem,
)
from .prompt import (
    NEGATIVE_BLOCK,
    PROMPT_BLOCK_ORDER,
    PROMPT_BLOCKS,
    CompiledPrompt,
    PromptBlocks,
)

#: The frozen public surface. `docs/ARCHITECTURE_MANIFEST.md` names this as the
#: shared language of the platform, and the boundary guard asserts that every
#: name here resolves and that nothing outside this package redefines one.
__all__ = [
    # generation
    "GENERATION_SPEC_FIELDS",
    "SPEC_SCHEMA_VERSION",
    "GenerationKind",
    "GenerationSpec",
    # prompt
    "NEGATIVE_BLOCK",
    "PROMPT_BLOCKS",
    "PROMPT_BLOCK_ORDER",
    "CompiledPrompt",
    "PromptBlocks",
    # persona
    "PERSONA_IDENTITY_FIELDS",
    "PersonaMemory",
    "PersonaProfile",
    "PersonaProfileSource",
    "PersonaSource",
    "PersonaStatus",
    "ReferenceImage",
    "WardrobeItem",
    # cinematic
    "ShotPreset",
    "ShotSource",
    "StylePreset",
    "StyleSource",
    # direction
    "DirectorIntent",
    "LanguageModel",
    "SceneBeat",
    # graph
    "GraphContext",
    "GraphContextSource",
]
