"""PR003: persistence repositories.

This package is the ONLY place in the application that turns SQLAlchemy
models into the product vocabulary and back. Routes and adapters (including
the Core's `MemoryResolver`, through a thin source adapter) depend on the
repositories — never on the models. Each repository opens short-lived
sessions per call (`SessionLocal`), the same convention `app.store.JobStore`
established in PR002, so instances are plain module-level singletons.
"""

from .persona_repository import (
    PERSONA_IMAGE_TYPES,
    PersonaRepository,
    PersonaRepositoryError,
    persona_repo,
    slugify,
)

__all__ = [
    "PersonaRepository",
    "PersonaRepositoryError",
    "PERSONA_IMAGE_TYPES",
    "persona_repo",
    "slugify",
]
