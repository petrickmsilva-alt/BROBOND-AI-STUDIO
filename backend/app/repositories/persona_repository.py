"""PR003: repository over the persona tables.

The single persistence boundary for the Persona Memory Engine:

* routes (``/api/v1/personas``) call it and return its rows as schemas;
* the Core's ``MemoryResolver`` reaches it only through two thin source
  adapters (``PersonaRepositoryIdentitySource`` / ``...ProfileSource``) that
  implement the Core protocols — the Core still never imports SQLAlchemy;
* the LoRA training flow reads the persona here instead of the in-memory
  dict, so training survives a restart.

Sessions are short-lived per call (``SessionLocal`` + explicit commit), the
same convention ``app.store.JobStore`` established in PR002. The module-level
``persona_repo`` singleton is what ``main`` wires in.

Child rows (``persona_images`` / ``persona_wardrobe`` /
``persona_identity_revision``) are removed explicitly by ``delete`` — this
repo follows the SQLite/Postgres-portable convention of the codebase (indexed
``persona_id`` references, no DB-level foreign keys).
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import delete as sa_delete, func, select
from sqlalchemy.orm import Session

from ..core.contracts import (
    PersonaMemory,
    PersonaProfile,
    PersonaStatus,
    ReferenceImage,
    WardrobeItem,
)
from ..db import SessionLocal
from ..models import Persona, PersonaIdentityRevision, PersonaImage, PersonaWardrobe

#: The product vocabulary for persona reference images.
PERSONA_IMAGE_TYPES = ("face", "body", "style", "reference")

#: Fields PATCH may touch. Identity fields bump the revision (see
#: ``PersonaIdentityRevision``); the rest are product metadata.
PROFILE_FIELDS = (
    "name",
    "age",
    "height",
    "body_type",
    "skin_tone",
    "hair",
    "beard",
    "eyes",
    "voice",
    "default_style",
    "lora_id",
)

#: The subset that, when changed, is an identity change in the ETAPA 4 sense.
IDENTITY_FIELDS = ("name", "age", "height", "body_type", "skin_tone", "hair", "beard", "eyes", "voice")


class PersonaRepositoryError(Exception):
    """Raised when a write cannot proceed (e.g. slug already taken)."""


def slugify(name: str) -> str:
    """Stable, workspace-unique-friendly slug from a persona name."""

    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug[:140] or "persona"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class PersonaRepository:
    """CRUD + relational reads for personas (workspace-scoped)."""

    # ------------------------------------------------------------- identity

    def to_memory(self, persona: Persona) -> PersonaMemory:
        """Map a row to the Core's identity object (``PersonaSource`` view).

        The mapping is lossy by design: the Core only knows identity fields,
        while the row carries the full product profile. `lora_path` stays
        None — the LoRA travels as an asset id (``lora_id``) that the worker
        resolves workspace-scoped, exactly like user-selected LoRAs.
        """

        images = self._images(persona.id)
        # PR004: the identity now carries the wardrobe names (comma joined).
        # The PERSONA prompt block renders them; the project-level selection
        # filters them afterwards (see `identity_phrase(wardrobe=...)`).
        wardrobe = ", ".join(item.name for item in self._wardrobe(persona.id))
        return PersonaMemory(
            persona_id=persona.id,
            name=persona.name,
            status=PersonaStatus.APPROVED,
            age=persona.age or None,
            height_m=persona.height or None,
            body_type=persona.body_type,
            hair=persona.hair,
            beard=persona.beard,
            eyes=persona.eyes,
            voice=persona.voice,
            wardrobe=wardrobe,
            default_style=persona.default_style,
            lora_path=None,
            reference_images=tuple(image.asset_id for image in images),
            version=persona.revision,
        )

    def to_profile(self, persona: Persona) -> PersonaProfile:
        """Map a row to the Core's full profile (``PersonaProfileSource``)."""

        wardrobe = tuple(
            WardrobeItem(name=item.name, category=item.category, metadata=_loads(item.metadata_json))
            for item in self._wardrobe(persona.id)
        )
        images = tuple(
            ReferenceImage(asset_id=image.asset_id, image_type=image.image_type, order_index=image.order_index)
            for image in self._images(persona.id)
        )
        return PersonaProfile(
            identity=self.to_memory(persona),
            wardrobe=wardrobe,
            lora_id=persona.lora_id,
            reference_images=images,
        )

    # ---------------------------------------------------------------- reads

    def find_by_id(self, persona_id: str, workspace_id: str | None = None) -> Persona | None:
        if not persona_id:
            return None
        with SessionLocal() as db:
            row = db.get(Persona, persona_id)
            if row is None:
                return None
            if workspace_id is not None and row.workspace_id != workspace_id:
                return None
            return _detach(db, row)

    def find_by_slug(self, slug: str, workspace_id: str) -> Persona | None:
        if not slug:
            return None
        with SessionLocal() as db:
            row = db.scalar(
                select(Persona).where(Persona.workspace_id == workspace_id, Persona.slug == slug)
            )
            return _detach(db, row) if row else None

    def list_workspace(self, workspace_id: str) -> list[Persona]:
        with SessionLocal() as db:
            rows = db.scalars(
                select(Persona).where(Persona.workspace_id == workspace_id).order_by(Persona.created_at)
            ).all()
            return [_detach(db, row) for row in rows]

    def images(self, persona_id: str) -> list[PersonaImage]:
        with SessionLocal() as db:
            rows = db.scalars(
                select(PersonaImage).where(PersonaImage.persona_id == persona_id).order_by(
                    PersonaImage.order_index, PersonaImage.id
                )
            ).all()
            return [_detach(db, row) for row in rows]

    def wardrobe(self, persona_id: str) -> list[PersonaWardrobe]:
        with SessionLocal() as db:
            # The row id is a random uuid and there is no order column, so
            # ordering by id would be non-deterministic across backends and
            # restarts. Name order is the stable, predictable rule the
            # identity phrase and the API share (PR004).
            rows = db.scalars(
                select(PersonaWardrobe).where(PersonaWardrobe.persona_id == persona_id).order_by(
                    func.lower(PersonaWardrobe.name)
                )
            ).all()
            return [_detach(db, row) for row in rows]

    def revisions(self, persona_id: str) -> list[PersonaIdentityRevision]:
        with SessionLocal() as db:
            rows = db.scalars(
                select(PersonaIdentityRevision)
                .where(PersonaIdentityRevision.persona_id == persona_id)
                .order_by(PersonaIdentityRevision.revision)
            ).all()
            return [_detach(db, row) for row in rows]

    # ---------------------------------------------------------------- writes

    def create(
        self,
        workspace_id: str,
        *,
        name: str,
        slug: str | None = None,
        age: int = 0,
        height: float = 0.0,
        body_type: str = "",
        skin_tone: str = "",
        hair: str = "",
        beard: str = "",
        eyes: str = "",
        voice: str = "",
        default_style: str = "",
        lora_id: str | None = None,
        reference_asset_ids: list[str] | None = None,
        actor_id: str = "",
    ) -> Persona:
        """Create the persona, its reference images and revision 1.

        Raises ``PersonaRepositoryError`` when the slug is already taken in
        the workspace (the unique constraint is the backstop).
        """

        persona_slug = slug or slugify(name)
        with SessionLocal() as db:
            taken = db.scalar(
                select(Persona.id).where(Persona.workspace_id == workspace_id, Persona.slug == persona_slug)
            )
            if taken:
                raise PersonaRepositoryError(f"slug '{persona_slug}' already exists in this workspace")
            persona = Persona(
                id=str(uuid4()),
                workspace_id=workspace_id,
                name=name,
                slug=persona_slug,
                age=age,
                height=height,
                body_type=body_type,
                skin_tone=skin_tone,
                hair=hair,
                beard=beard,
                eyes=eyes,
                voice=voice,
                default_style=default_style,
                lora_id=lora_id,
                revision=1,
                created_at=_utcnow(),
                updated_at=_utcnow(),
            )
            db.add(persona)
            for index, asset_id in enumerate(reference_asset_ids or []):
                db.add(
                    PersonaImage(
                        id=str(uuid4()),
                        persona_id=persona.id,
                        asset_id=asset_id,
                        image_type="reference",
                        order_index=index,
                    )
                )
            db.add(
                PersonaIdentityRevision(
                    id=str(uuid4()),
                    persona_id=persona.id,
                    revision=1,
                    notes=json.dumps({"created": True, "fields": list(PROFILE_FIELDS)}, ensure_ascii=False),
                    created_by=actor_id,
                    created_at=_utcnow(),
                )
            )
            db.commit()
            return _detach(db, persona)

    def update(
        self,
        persona_id: str,
        changes: dict[str, object],
        *,
        actor_id: str = "",
        wardrobe_items: list[dict[str, object]] | None = None,
    ) -> Persona | None:
        """Apply a partial update; identity changes bump the revision.

        `changes` keys are validated against ``PROFILE_FIELDS`` (unknown keys
        are ignored — the API layer has already validated the shape). When at
        least one identity field changes, ``persona.revision`` is incremented
        and a ``persona_identity_revision`` row is appended (never rewritten).
        """

        changes = {key: value for key, value in changes.items() if key in PROFILE_FIELDS}
        identity_changes = {key: value for key, value in changes.items() if key in IDENTITY_FIELDS}
        with SessionLocal() as db:
            persona = db.get(Persona, persona_id)
            if persona is None:
                return None
            for key, value in changes.items():
                setattr(persona, key, value)
            if identity_changes:
                persona.revision += 1
                db.add(
                    PersonaIdentityRevision(
                        id=str(uuid4()),
                        persona_id=persona.id,
                        revision=persona.revision,
                        notes=json.dumps({"changed": identity_changes}, ensure_ascii=False),
                        created_by=actor_id,
                        created_at=_utcnow(),
                    )
                )
            if wardrobe_items is not None:
                db.execute(sa_delete(PersonaWardrobe).where(PersonaWardrobe.persona_id == persona_id))
                for item in wardrobe_items:
                    db.add(
                        PersonaWardrobe(
                            id=str(uuid4()),
                            persona_id=persona_id,
                            name=str(item.get("name", "")),
                            category=str(item.get("category", "")),
                            metadata_json=json.dumps(dict(item.get("metadata") or {}), ensure_ascii=False),
                        )
                    )
            persona.updated_at = _utcnow()
            db.commit()
            return _detach(db, persona)

    def delete(self, persona_id: str) -> bool:
        """Remove the persona and all its child rows.

        Reference *assets* are untouched — the persona only pointed at them.
        Training-run history keeps its ``persona_id`` string (append-only).
        """

        with SessionLocal() as db:
            persona = db.get(Persona, persona_id)
            if persona is None:
                return False
            for model in (PersonaImage, PersonaWardrobe, PersonaIdentityRevision):
                db.execute(sa_delete(model).where(model.persona_id == persona_id))
            db.delete(persona)
            db.commit()
            return True

    def attach_image(self, persona_id: str, asset_id: str, image_type: str, order_index: int | None = None) -> PersonaImage | None:
        """Attach a stored asset to the persona.

        Returns None when the persona does not exist or the asset is already
        attached (the route turns that into 404 / 409).
        """

        with SessionLocal() as db:
            persona = db.get(Persona, persona_id)
            if persona is None:
                return None
            existing = db.scalar(
                select(PersonaImage).where(
                    PersonaImage.persona_id == persona_id, PersonaImage.asset_id == asset_id
                )
            )
            if existing is not None:
                return None
            if order_index is None:
                count = db.scalar(
                    select(func.count()).select_from(PersonaImage).where(PersonaImage.persona_id == persona_id)
                )
                order_index = int(count or 0)
            image = PersonaImage(
                id=str(uuid4()),
                persona_id=persona_id,
                asset_id=asset_id,
                image_type=image_type,
                order_index=order_index,
            )
            db.add(image)
            db.commit()
            return _detach(db, image)

    def set_lora(self, persona_id: str, lora_id: str | None) -> Persona | None:
        """Point the persona at a trained LoRA asset (or clear it)."""

        return self.update(persona_id, {"lora_id": lora_id})

    def replace_references(self, persona_id: str, asset_ids: list[str]) -> bool:
        """Replace the persona's `reference`-type images with `asset_ids`.

        The legacy training contract: queueing training refreshes the persona
        with the exact reference set the run will use. `face`/`body`/`style`
        images are untouched. Returns False when the persona does not exist.
        """

        with SessionLocal() as db:
            persona = db.get(Persona, persona_id)
            if persona is None:
                return False
            db.execute(
                sa_delete(PersonaImage).where(
                    PersonaImage.persona_id == persona_id, PersonaImage.image_type == "reference"
                )
            )
            for index, asset_id in enumerate(asset_ids):
                db.add(
                    PersonaImage(
                        id=str(uuid4()),
                        persona_id=persona_id,
                        asset_id=asset_id,
                        image_type="reference",
                        order_index=index,
                    )
                )
            db.commit()
            return True

    # -------------------------------------------------------------- internal

    def _images(self, persona_id: str) -> list[PersonaImage]:
        return self.images(persona_id)

    def _wardrobe(self, persona_id: str) -> list[PersonaWardrobe]:
        return self.wardrobe(persona_id)


def _loads(raw: str) -> dict[str, object]:
    try:
        value = json.loads(raw or "{}")
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        return {}


def _detach(db: Session, row):
    """Return a detached row whose attributes are fully loaded.

    `db.commit()` expires the instance by default; refreshing before
    expunging loads every column into memory, so the caller can keep using
    the row after the session closes without a DetachedInstanceError.
    """

    db.refresh(row)
    db.expunge(row)
    return row


#: The module-level singleton the API layer wires in (mirrors
#: ``app.store.job_store`` from PR002).
persona_repo = PersonaRepository()
