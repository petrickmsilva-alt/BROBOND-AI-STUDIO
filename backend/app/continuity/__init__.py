"""V3.2 — Character Continuity Engine.

Absolute continuity across scenes, episodes and campaigns: five locks
freeze what a character looks like, wears, where the story happens, what it
drives and how it sounds — and the resolver answers "what is locked for
this character, in this campaign, in this episode?" as one
``ContinuityContext``.

Layering (same rule as ``graph/``): the five lock modules and the resolver
are framework-free and reason over frozen snapshots; ``continuity_models``
holds the SQLAlchemy tables; ``continuity_repository`` is the only module
that touches the database. ``identity_lock`` additionally hosts the package
kernel (the shared validation error, the canonical fingerprint and the key
normalisation) so each exists exactly once.

The Director AI, the Provider Registry and the Render Engine are not
altered: continuity enriches the cinematic context, it never rewrites the
``GenerationSpec``.
"""
from .continuity_models import (
    DEFAULT_CAMPAIGN,
    DEFAULT_EPISODE,
    LOCK_TYPES,
    ContinuityEpisode,
    ContinuityLock,
    dumps_payload,
    loads_payload,
    normalize_lock_type,
    utcnow,
)
from .continuity_repository import (
    ContinuityEpisodeView,
    ContinuityLockView,
    ContinuityRepository,
    ContinuityRepositoryError,
    RepositoryContinuityStore,
    continuity_repo,
    continuity_store_for,
    episode_view,
    lock_view,
)
from .continuity_resolver import (
    LOCK_ORDER,
    ContinuityContext,
    ContinuityResolver,
    ContinuityStore,
    StoredLock,
)
from .identity_lock import (
    IDENTITY_FIELDS,
    ContinuityValidationError,
    IdentityLock,
    IdentitySnapshot,
    clean_field,
    fingerprint_for,
    normalize_campaign,
    normalize_episode,
    normalize_persona_id,
)
from .location_lock import LOCATION_FIELDS, LOCATION_VENUES, LocationLock, LocationSnapshot
from .vehicle_lock import VEHICLE_FIELDS, VehicleLock, VehicleSnapshot
from .voice_lock import VOICE_FIELDS, VoiceLock, VoiceSnapshot
from .wardrobe_lock import WARDROBE_FIELDS, WardrobeLock, WardrobeSnapshot

__all__ = [
    "DEFAULT_CAMPAIGN",
    "DEFAULT_EPISODE",
    "IDENTITY_FIELDS",
    "LOCATION_FIELDS",
    "LOCATION_VENUES",
    "LOCK_ORDER",
    "LOCK_TYPES",
    "VEHICLE_FIELDS",
    "VOICE_FIELDS",
    "WARDROBE_FIELDS",
    "ContinuityContext",
    "ContinuityEpisode",
    "ContinuityEpisodeView",
    "ContinuityLock",
    "ContinuityLockView",
    "ContinuityRepository",
    "ContinuityRepositoryError",
    "ContinuityResolver",
    "ContinuityStore",
    "ContinuityValidationError",
    "IdentityLock",
    "IdentitySnapshot",
    "LocationLock",
    "LocationSnapshot",
    "RepositoryContinuityStore",
    "StoredLock",
    "VehicleLock",
    "VehicleSnapshot",
    "VoiceLock",
    "VoiceSnapshot",
    "WardrobeLock",
    "WardrobeSnapshot",
    "clean_field",
    "continuity_repo",
    "continuity_store_for",
    "dumps_payload",
    "episode_view",
    "fingerprint_for",
    "loads_payload",
    "lock_view",
    "normalize_campaign",
    "normalize_episode",
    "normalize_lock_type",
    "normalize_persona_id",
    "utcnow",
]
