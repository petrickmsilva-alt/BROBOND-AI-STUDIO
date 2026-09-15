"""PR004 — Studio Persona Pipeline: the persona flows end to end.

Covers the acceptance criteria of the brief:

* the compiler resolves the persona's wardrobe into the PERSONA prompt block,
  optionally narrowed to the items the project selected (ETAPA 3);
* the generation request schemas accept the pipeline fields (`persona_id`,
  `style`, `wardrobe`, `camera_motion`) without changing the GenerationSpec
  contract (ETAPAS 3/4/5);
* the worker auto-resolves the persona's own reference image (face first)
  when the job carries no explicit reference (ETAPA 3);
* the studio frontend is structurally wired: PersonaSelector and
  PersonaPreview exist, both studios carry the identity panel, the payloads
  include `persona_id`, the topbar shows the active identity, the sidebar
  has the Studio group and the Project Memory persists/restores the four
  fields (ETAPAS 1/2/4/5/6/7).

The frontend has no JavaScript test runner in this repository (same rule as
`test_frontend_honesty.py`): its tests are structural guards that read the
source and assert on what is there.
"""
from __future__ import annotations

import pathlib
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from app.core.contracts import PersonaMemory, PersonaStatus
from app.main import app, memory_resolver

client = TestClient(app)

ROOT = pathlib.Path(__file__).resolve().parents[2]
PAGE = ROOT / "app" / "page.tsx"
SELECTOR = ROOT / "app" / "components" / "studio" / "PersonaSelector.tsx"
PREVIEW = ROOT / "app" / "components" / "studio" / "PersonaPreview.tsx"
PROJECT_MEMORY = ROOT / "lib" / "projectMemory.ts"


# --------------------------------------------------------------------- helpers


def _token() -> dict:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": f"pr004-{uuid4()}@example.com", "name": "Studio Pipeline", "password": "strong-pass-123"},
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _create_persona_with_wardrobe(headers: dict) -> dict:
    response = client.post(
        "/api/v1/personas",
        headers=headers,
        json={
            "name": f"Pipeline {uuid4().hex[:6]}",
            "age": 38,
            "appearance": "Athletic",
            "eye_color": "Dark brown",
            "hair": "Short",
            "beard": "Stubble",
            "height_m": 1.80,
            "style": "cinematic noir",
        },
    )
    assert response.status_code in (200, 201, 202), response.text
    persona = response.json()
    wardrobe = [
        {"name": "leather jacket", "category": "jacket", "metadata": {}},
        {"name": "red dress", "category": "dress", "metadata": {}},
    ]
    response = client.patch(f"/api/v1/personas/{persona['id']}", headers=headers, json={"wardrobe": wardrobe})
    assert response.status_code == 200, response.text
    return persona


# --------------------------------------------------------------------- unit
# The identity phrase and the wardrobe filter (no database involved)


def _memory(wardrobe: str = "leather jacket, red dress") -> PersonaMemory:
    return PersonaMemory(
        persona_id="p-test",
        name="Pipeline Persona",
        status=PersonaStatus.APPROVED,
        age=38,
        height_m=1.80,
        body_type="athletic",
        hair="short",
        beard="stubble",
        eyes="dark brown",
        voice="warm baritone",
        wardrobe=wardrobe,
        default_style="cinematic noir",
    )


def test_identity_phrase_includes_the_full_wardrobe() -> None:
    phrase = memory_resolver.identity_phrase(_memory())
    assert "wardrobe: leather jacket, red dress" in phrase


def test_identity_phrase_filters_the_wardrobe_to_the_selection() -> None:
    phrase = memory_resolver.identity_phrase(_memory(), wardrobe=["red dress"])
    assert "wardrobe: red dress" in phrase
    assert "leather jacket" not in phrase


def test_identity_phrase_with_a_selection_that_matches_nothing_drops_the_block_part() -> None:
    phrase = memory_resolver.identity_phrase(_memory(), wardrobe=["ghost outfit"])
    assert "wardrobe" not in phrase
    # The identity itself must survive the empty wardrobe filter.
    assert "Pipeline Persona, 38 years old" in phrase


def test_identity_phrase_without_a_wardrobe_keeps_the_legacy_shape() -> None:
    phrase = memory_resolver.identity_phrase(_memory(wardrobe=""))
    assert "wardrobe" not in phrase
    assert phrase.startswith("Pipeline Persona, ")


# ------------------------------------------------------------------- compile
# ETAPA 3: POST /core/compile resolves identity, style, LoRA, wardrobe


def test_compile_resolves_the_persona_wardrobe_from_the_persistent_store() -> None:
    headers = _token()
    persona = _create_persona_with_wardrobe(headers)
    response = client.post(
        "/api/v1/core/compile",
        headers=headers,
        json={"prompt": "walking through the city", "persona_id": persona["id"]},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    # Identity AND wardrobe reach the compiled prompt, resolved automatically.
    # The create response is a legacy envelope; the name lives in `details`.
    assert f"{persona['details']['name']}, 38 years old, 1.80m tall" in body["prompt_compiled"]
    assert "wardrobe: leather jacket, red dress" in body["prompt_compiled"]
    assert body["persona_id"] == persona["id"]
    assert body["style_id"] is not None


def test_compile_narrows_the_wardrobe_to_the_project_selection() -> None:
    headers = _token()
    persona = _create_persona_with_wardrobe(headers)
    response = client.post(
        "/api/v1/core/compile",
        headers=headers,
        json={"prompt": "walking through the city", "persona_id": persona["id"], "wardrobe": ["red dress"]},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert "wardrobe: red dress" in body["prompt_compiled"]
    assert "leather jacket" not in body["prompt_compiled"]


def test_compile_without_a_persona_is_unaffected() -> None:
    response = client.post("/api/v1/core/compile", json={"prompt": "an empty street at night"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert "wardrobe" not in body["prompt_compiled"]
    assert body["persona_id"] is None


def test_generation_requests_accept_the_pipeline_fields() -> None:
    """ETAPAS 3/4/5: the schemas accept persona_id, style, wardrobe and
    camera_motion. The GenerationSpec contract itself is untouched — these
    fields are resolution inputs, not spec fields."""

    headers = _token()
    persona = _create_persona_with_wardrobe(headers)

    image = client.post(
        "/api/v1/generations/images",
        headers=headers,
        json={
            "prompt": "a directed frame",
            "persona_id": persona["id"],
            "style": "cinematic noir",
            "wardrobe": ["red dress"],
        },
    )
    assert image.status_code == 202, image.text
    assert image.json()["status"] == "queued"

    video = client.post(
        "/api/v1/generations/videos",
        headers=headers,
        json={
            "prompt": "a directed sequence",
            "persona_id": persona["id"],
            "style": "cinematic noir",
            "wardrobe": ["leather jacket"],
            "camera_motion": "tracking",
        },
    )
    assert video.status_code == 202, video.text


def test_job_parameters_carry_the_pipeline_into_the_spec_builder() -> None:
    """The worker path (spec_adapter.compile_job) must forward the pipeline
    fields so a queued generation resolves exactly like /core/compile does."""

    from app.spec_adapter import _shared_kwargs

    class _Job:
        prompt = "a directed frame"
        type = "image"
        model = "flux-dev"
        parameters = {
            "persona_id": "p-1",
            "style": "cinematic noir",
            "wardrobe": ["red dress"],
            "workspace_id": "w-1",
        }

    kwargs = _shared_kwargs(_Job(), _Job.parameters)
    assert kwargs["persona_id"] == "p-1"
    assert kwargs["style"] == "cinematic noir"
    assert kwargs["wardrobe"] == ["red dress"]


# ------------------------------------------------------------- worker (ETAPA 3)


def _seed_reference_database():
    """A throwaway in-memory database with the worker's reference rules."""
    from app.db import Base
    from app.models import Asset, PersonaImage, Workspace

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(Workspace.__table__.insert().values(id="w-1", name="Workspace", owner_id="u-1"))
        connection.execute(Asset.__table__.insert().values(id="a-face", workspace_id="w-1", name="face.jpg", kind="image", object_key="persona/face.jpg"))
        connection.execute(Asset.__table__.insert().values(id="a-body", workspace_id="w-1", name="body.jpg", kind="image", object_key="persona/body.jpg"))
        connection.execute(Asset.__table__.insert().values(id="a-other-ws", workspace_id="w-2", name="other.jpg", kind="image", object_key="other.jpg"))
        connection.execute(Asset.__table__.insert().values(id="a-video", workspace_id="w-1", name="clip.mp4", kind="video", object_key="clip.mp4"))
        connection.execute(PersonaImage.__table__.insert().values(id="pi-1", persona_id="p-1", asset_id="a-body", image_type="body", order_index=0))
        connection.execute(PersonaImage.__table__.insert().values(id="pi-2", persona_id="p-1", asset_id="a-face", image_type="face", order_index=5))
        connection.execute(PersonaImage.__table__.insert().values(id="pi-3", persona_id="p-2", asset_id="a-other-ws", image_type="face", order_index=0))
        connection.execute(PersonaImage.__table__.insert().values(id="pi-4", persona_id="p-3", asset_id="a-video", image_type="face", order_index=0))
    return engine


def test_worker_picks_the_face_reference_first() -> None:
    from sqlalchemy.orm import Session

    from app.queue import _persona_reference_object_key

    engine = _seed_reference_database()
    try:
        with Session(bind=engine) as session:
            key = _persona_reference_object_key("p-1", "w-1", session)
    finally:
        engine.dispose()
    assert key == "persona/face.jpg"


def test_worker_falls_back_to_display_order_without_a_face() -> None:
    from sqlalchemy import delete
    from sqlalchemy.orm import Session

    from app.models import PersonaImage
    from app.queue import _persona_reference_object_key

    engine = _seed_reference_database()
    try:
        with Session(bind=engine) as session:
            session.execute(delete(PersonaImage).where(PersonaImage.id == "pi-2"))
            session.commit()
            key = _persona_reference_object_key("p-1", "w-1", session)
    finally:
        engine.dispose()
    assert key == "persona/body.jpg"


def test_worker_never_crosses_workspace_ownership() -> None:
    from sqlalchemy.orm import Session

    from app.queue import _persona_reference_object_key

    engine = _seed_reference_database()
    try:
        with Session(bind=engine) as session:
            # p-2's face lives in w-2: for w-1 the job must run without a
            # reference instead of stealing another tenant's image.
            assert _persona_reference_object_key("p-2", "w-1", session) is None
            # ...but inside its own workspace the same persona resolves.
            assert _persona_reference_object_key("p-2", "w-2", session) == "other.jpg"
    finally:
        engine.dispose()


def test_worker_skips_non_image_references() -> None:
    from sqlalchemy.orm import Session

    from app.queue import _persona_reference_object_key

    engine = _seed_reference_database()
    try:
        with Session(bind=engine) as session:
            assert _persona_reference_object_key("p-3", "w-1", session) is None
    finally:
        engine.dispose()


def test_worker_wires_the_auto_reference_into_the_generation_flow() -> None:
    """Structural guard: the Celery task must call the resolver when the job
    carries a persona and no explicit reference (the unit tests above pin the
    resolver; this pins the wiring)."""

    import inspect

    from app import queue

    source = inspect.getsource(queue.process_generation)
    assert "_persona_reference_object_key" in source
    assert 'parameters.get("persona_id")' in source


# ----------------------------------------------------- frontend (structural)


def _read(path: pathlib.Path) -> str:
    assert path.is_file(), f"{path} is missing"
    return path.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def page_source() -> str:
    return _read(PAGE)


@pytest.fixture(scope="module")
def selector_source() -> str:
    return _read(SELECTOR)


@pytest.fixture(scope="module")
def preview_source() -> str:
    return _read(PREVIEW)


@pytest.fixture(scope="module")
def memory_source() -> str:
    return _read(PROJECT_MEMORY)


# ETAPA 1 — PersonaSelector


def test_selector_exists_and_is_reusable() -> None:
    source = _read(SELECTOR)
    assert "export default function PersonaSelector" in source
    # Search by name, avatar, default style, LoRA indicator and selection.
    assert "Search persona..." in source
    assert "onSelect" in source
    assert "default_style" in source
    assert "lora_id" in source


def test_selector_is_used_by_both_studios(page_source: str) -> None:
    assert "from './components/studio/PersonaSelector'" in page_source
    # Both studios render the identity panel with the selector inside it.
    assert page_source.count("<IdentityPanel") == 2


# ETAPA 2 — PersonaPreview


def test_preview_shows_the_identity_and_the_wardrobe(preview_source: str) -> None:
    for field in ("Beard", "Hair", "Voice", "Default style", "LoRA", "Wardrobe"):
        assert field in preview_source, f"missing field: {field}"
    # Real-time: pure render of the persona prop, keyed for the transition.
    assert "key={persona.id}" in preview_source


# ETAPAS 4/5 — the studios carry the pipeline in their payloads


def test_image_studio_sends_the_pipeline(page_source: str) -> None:
    assert "persona_id: activePersona?.id || undefined" in page_source
    assert "style: style || undefined" in page_source
    assert "wardrobe: selectedWardrobe.length ? selectedWardrobe : undefined" in page_source
    # ETAPA 4: the "Usar estilo da Persona" shortcut exists in the studio.
    assert "Usar estilo da Persona" in page_source


def test_video_studio_adds_camera_and_duration(page_source: str) -> None:
    # Duration was already a control; ETAPA 5 adds camera, persona and style.
    assert 'camera_motion: cameraMotion' in page_source
    assert "duration_seconds: duration" in page_source
    assert "[5, 10, 15]" in page_source
    assert "'static', 'pan', 'tilt', 'zoom', 'tracking', 'crane'" in page_source


# ETAPA 6 — Project Memory


def test_project_memory_persists_the_four_fields(memory_source: str) -> None:
    for field in ("persona_id", "default_style", "last_lora", "selected_wardrobe"):
        assert field in memory_source, f"missing field: {field}"
    assert "loadProjectMemory" in memory_source
    assert "saveProjectMemory" in memory_source


def test_project_memory_restores_and_persists_in_home(page_source: str) -> None:
    # PR004.1: Home consumes the hook (which consumes the adapter) — it never
    # names the v0 API or the storage key directly.
    assert "useProjectMemory(PROJECT_ID)" in page_source
    # Restore: the saved persona/style/wardrobe/LoRA (official field names)
    # come back on load.
    assert "memory.personaId" in page_source
    assert "memory.loraId" in page_source
    assert "memory.styleId" in page_source
    assert "memory.wardrobeId" in page_source
    # Persist: the state is saved on every change via the hook.
    assert "saveMemory({" in page_source


# ETAPA 7 — sidebar Studio group and the active identity in the topbar


def test_sidebar_has_the_studio_group(page_source: str) -> None:
    assert 'STUDIO' in page_source
    for label in ("Personas", "Image", "Video", "Projects"):
        assert label in page_source, f"missing sidebar entry: {label}"


def test_topbar_shows_the_active_identity(page_source: str) -> None:
    assert "active-identity" in page_source
    assert "activePersona?.name" in page_source or "activePersona.name" in page_source
