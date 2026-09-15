"""PR003 — Persona Memory Engine: persistence, isolation, revisions, resolver.

Covers the acceptance criteria of the brief:

* CRUD on the profile endpoints (persisted in PostgreSQL via Alembic 0002);
* workspace isolation (foreign personas behave as 404, never 403);
* the slug is unique per workspace;
* the append-only identity-revision history (bumped only by identity changes);
* image references (attach only existing image assets, no upload here);
* the MemoryResolver `resolve_persona` path the GenerationSpec uses
  (persistent persona identity reaching the compiled prompt) and the LoRA
  inheritance on generation requests.
"""
from __future__ import annotations

import pathlib
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text

from app.main import app, memory_resolver

client = TestClient(app)

ROOT = pathlib.Path(__file__).resolve().parents[2]


# --------------------------------------------------------------------- helpers


def _token() -> dict:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": f"persona-{uuid4()}@example.com", "name": "Persona Engine", "password": "strong-pass-123"},
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _upload(headers: dict, name: str = "face.jpg", kind: str = "image/jpeg") -> dict:
    response = client.post(
        "/api/v1/assets/upload", headers=headers, files={"file": (name, b"fake-image-bytes", kind)}
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_persona(headers: dict, **overrides) -> dict:
    payload = {
        "name": overrides.pop("name", "Rafaela Costa"),
        "age": overrides.pop("age", 34),
        "appearance": overrides.pop("appearance", "Slender"),
        "eye_color": overrides.pop("eye_color", "Amber"),
        "height_m": overrides.pop("height_m", 1.72),
        "style": overrides.pop("style", "cinematic realism"),
        **overrides,
    }
    response = client.post("/api/v1/personas", headers=headers, json=payload)
    assert response.status_code == 202, response.text
    return response.json()


# ----------------------------------------------------------------------- CRUD


def test_create_persona_persists_the_profile() -> None:
    headers = _token()
    created = _create_persona(headers, beard="light stubble", hair="wavy dark")

    response = client.get(f"/api/v1/personas/{created['id']}", headers=headers)
    assert response.status_code == 200, response.text
    profile = response.json()
    assert profile["id"] == created["id"]
    assert profile["name"] == "Rafaela Costa"
    assert profile["slug"] == "rafaela-costa"
    assert profile["age"] == 34
    assert profile["height"] == 1.72
    assert profile["body_type"] == "Slender"
    assert profile["eyes"] == "Amber"
    assert profile["default_style"] == "cinematic realism"
    assert profile["revision"] == 1
    assert profile["lora_id"] is None
    assert profile["images"] == []
    assert profile["wardrobe"] == []
    # Creation is revision 1 of the append-only history.
    assert [revision["revision"] for revision in profile["revisions"]] == [1]
    assert profile["revisions"][0]["created_by"]


def test_list_personas_returns_only_the_workspace() -> None:
    mine = _token()
    other = _token()
    _create_persona(mine, name="First Persona")
    _create_persona(mine, name="Second Persona")
    _create_persona(other, name="Someone Else")

    response = client.get("/api/v1/personas", headers=mine)
    assert response.status_code == 200
    names = {profile["name"] for profile in response.json()}
    assert names == {"First Persona", "Second Persona"}


def test_delete_persona_removes_profile_and_children() -> None:
    headers = _token()
    created = _create_persona(headers)
    asset = _upload(headers)
    assert client.post(f"/api/v1/personas/{created['id']}/images", headers=headers, json={"asset_id": asset["id"]}).status_code == 201
    assert client.patch(f"/api/v1/personas/{created['id']}", headers=headers, json={"hair": "short"}).status_code == 200

    assert client.delete(f"/api/v1/personas/{created['id']}", headers=headers).status_code == 204
    assert client.get(f"/api/v1/personas/{created['id']}", headers=headers).status_code == 404
    assert client.delete(f"/api/v1/personas/{created['id']}", headers=headers).status_code == 404
    assert [profile["id"] for profile in client.get("/api/v1/personas", headers=headers).json()] == []


# --------------------------------------------------------------------- slugs


def test_slug_is_unique_per_workspace() -> None:
    mine = _token()
    other = _token()
    assert _create_persona(mine, name="Dup Persona")["id"]

    duplicate = client.post(
        "/api/v1/personas",
        headers=mine,
        json={"name": "dup persona!!", "age": 20, "appearance": "Petite", "eye_color": "Blue", "height_m": 1.6, "style": "noir"},
    )
    assert duplicate.status_code == 409, duplicate.text

    # The same name in another workspace is fine: uniqueness is per tenant.
    assert _create_persona(other, name="Dup Persona")["id"]


# ---------------------------------------------------------------- isolation


def test_foreign_personas_are_invisible_to_other_tenants() -> None:
    mine = _token()
    other = _token()
    created = _create_persona(mine)

    assert client.get(f"/api/v1/personas/{created['id']}", headers=other).status_code == 404
    assert client.patch(f"/api/v1/personas/{created['id']}", headers=other, json={"hair": "x"}).status_code == 404
    assert client.delete(f"/api/v1/personas/{created['id']}", headers=other).status_code == 404
    assert client.get(f"/api/v1/personas/{created['id']}/images", headers=other).status_code == 404

    response = client.post(f"/api/v1/personas/{created['id']}/images", headers=other, json={"asset_id": str(uuid4())})
    assert response.status_code == 404
    # And the original owner still sees everything.
    assert client.get(f"/api/v1/personas/{created['id']}", headers=mine).status_code == 200


# ----------------------------------------------------------------- revisions


def test_identity_changes_bump_the_revision_history() -> None:
    headers = _token()
    created = _create_persona(headers)
    profile_url = f"/api/v1/personas/{created['id']}"

    response = client.patch(profile_url, headers=headers, json={"age": 35, "eyes": "hazel"})
    assert response.status_code == 200, response.text
    profile = response.json()
    assert profile["revision"] == 2
    assert profile["age"] == 35
    assert profile["eyes"] == "hazel"
    latest = profile["revisions"][-1]
    assert latest["revision"] == 2
    assert latest["notes"]["changed"] == {"age": 35, "eyes": "hazel"}
    # The history is append-only: revision 1 is still there, unmodified.
    assert [revision["revision"] for revision in profile["revisions"]] == [1, 2]


def test_non_identity_changes_do_not_bump_the_revision() -> None:
    headers = _token()
    created = _create_persona(headers)
    response = client.patch(
        f"/api/v1/personas/{created['id']}",
        headers=headers,
        json={"default_style": "neon noir", "lora_id": str(uuid4())},
    )
    assert response.status_code == 200, response.text
    profile = response.json()
    assert profile["revision"] == 1
    assert len(profile["revisions"]) == 1
    assert profile["default_style"] == "neon noir"
    assert profile["lora_id"] is not None


def test_wardrobe_is_replaced_on_update() -> None:
    headers = _token()
    created = _create_persona(headers)
    wardrobe = [
        {"name": "leather jacket", "category": "jacket", "metadata": {"era": "80s"}},
        {"name": "red dress", "category": "dress", "metadata": {}},
    ]
    response = client.patch(f"/api/v1/personas/{created['id']}", headers=headers, json={"wardrobe": wardrobe})
    assert response.status_code == 200, response.text
    saved = response.json()["wardrobe"]
    assert {item["name"] for item in saved} == {"leather jacket", "red dress"}
    jacket = next(item for item in saved if item["name"] == "leather jacket")
    assert jacket["category"] == "jacket"
    assert jacket["metadata"] == {"era": "80s"}

    replacement = [{"name": "suit", "category": "formal", "metadata": {}}]
    response = client.patch(f"/api/v1/personas/{created['id']}", headers=headers, json={"wardrobe": replacement})
    assert [item["name"] for item in response.json()["wardrobe"]] == ["suit"]


# -------------------------------------------------------------------- images


def test_images_attach_only_existing_image_assets() -> None:
    mine = _token()
    other = _token()
    created = _create_persona(mine)
    image = _upload(mine, "portrait.jpg")
    video = _upload(mine, "clip.mp4", kind="video/mp4")

    attached = client.post(
        f"/api/v1/personas/{created['id']}/images",
        headers=mine,
        json={"asset_id": image["id"], "image_type": "face"},
    )
    assert attached.status_code == 201, attached.text
    body = attached.json()
    assert body["asset_id"] == image["id"]
    assert body["image_type"] == "face"
    assert body["order_index"] == 0
    assert body["name"] == "portrait.jpg"

    # Re-attaching the same asset is a conflict.
    assert client.post(f"/api/v1/personas/{created['id']}/images", headers=mine, json={"asset_id": image["id"]}).status_code == 409
    # Non-image assets cannot be referenced.
    assert client.post(f"/api/v1/personas/{created['id']}/images", headers=mine, json={"asset_id": video["id"]}).status_code == 422
    # Another tenant's asset is invisible (404, not 403).
    assert client.post(f"/api/v1/personas/{created['id']}/images", headers=other, json={"asset_id": image["id"]}).status_code == 404
    # Unknown asset ids 404.
    assert client.post(f"/api/v1/personas/{created['id']}/images", headers=mine, json={"asset_id": str(uuid4())}).status_code == 404


def test_images_list_joins_assets_and_survives_missing_ones() -> None:
    headers = _token()
    created = _create_persona(headers, reference_asset_ids=[str(uuid4()), str(uuid4())])
    asset = _upload(headers, "body.jpg")
    client.post(f"/api/v1/personas/{created['id']}/images", headers=headers, json={"asset_id": asset["id"], "image_type": "body", "order_index": 10})

    listed = client.get(f"/api/v1/personas/{created['id']}/images", headers=headers).json()
    assert len(listed) == 3
    by_asset = {image["asset_id"]: image for image in listed}
    real = by_asset[asset["id"]]
    assert real["image_type"] == "body"
    assert real["order_index"] == 10
    assert real["name"] == "body.jpg"
    assert real["url"]
    for image in listed:
        if image["asset_id"] not in (asset["id"],):
            assert image["name"] is None
            assert image["url"] is None
            assert image["image_type"] == "reference"


def test_training_refreshes_the_reference_set() -> None:
    headers = _token()
    created = _create_persona(headers)
    references = [str(uuid4()) for _ in range(20)]
    response = client.post(f"/api/v1/personas/{created['id']}/train", headers=headers, json={"reference_asset_ids": references})
    assert response.status_code == 202, response.text

    profile = client.get(f"/api/v1/personas/{created['id']}", headers=headers).json()
    assert sorted(image["asset_id"] for image in profile["images"]) == sorted(references)
    assert all(image["image_type"] == "reference" for image in profile["images"])


# ------------------------------------------------------------- MemoryResolver


def test_resolver_returns_the_persistent_profile() -> None:
    headers = _token()
    created = _create_persona(headers, beard="full")
    asset = _upload(headers, "style.jpg")
    client.post(f"/api/v1/personas/{created['id']}/images", headers=headers, json={"asset_id": asset["id"], "image_type": "style"})
    client.patch(f"/api/v1/personas/{created['id']}", headers=headers, json={"wardrobe": [{"name": "trench coat", "category": "coat", "metadata": {}}]})

    profile = memory_resolver.resolve_persona(created["id"])
    assert profile is not None
    assert profile.persona_id == created["id"]
    assert profile.identity.name == "Rafaela Costa"
    assert profile.identity.beard == "full"
    assert profile.identity.status.value == "approved"
    assert [item.name for item in profile.wardrobe] == ["trench coat"]
    assert [reference.asset_id for reference in profile.reference_images] == [asset["id"]]
    assert profile.reference_images[0].image_type == "style"


def test_resolver_falls_back_to_ledger_and_missing() -> None:
    # A character known only to the ledger still resolves, without wardrobe/LoRA.
    charles = memory_resolver.resolve_persona("CHAR_PETRICK")
    assert charles is not None
    assert charles.wardrobe == ()
    assert charles.lora_id is None
    assert memory_resolver.resolve_persona("does-not-exist") is None
    assert memory_resolver.resolve_persona(None) is None


def test_compile_uses_the_persistent_persona_memory() -> None:
    """The GenerationSpec builder must see a persona stored in PostgreSQL."""

    headers = _token()
    created = _create_persona(headers)
    response = client.post(
        "/api/v1/core/compile",
        headers=headers,
        json={"prompt": "walking through the city", "persona_id": created["id"]},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    # The identity phrase (name + age + height + body + eyes) reaches the prompt.
    assert "Rafaela Costa, 34 years old, 1.72m tall" in body["prompt_compiled"]
    assert body["persona_id"] == created["id"]

    # Without the persona the phrase is absent.
    baseline = client.post("/api/v1/core/compile", headers=headers, json={"prompt": "walking through the city"}).json()
    assert "Rafaela Costa" not in baseline["prompt_compiled"]


def test_generation_inherits_the_persona_lora() -> None:
    headers = _token()
    created = _create_persona(headers)
    lora = str(uuid4())
    assert client.patch(f"/api/v1/personas/{created['id']}", headers=headers, json={"lora_id": lora}).status_code == 200

    response = client.post(
        "/api/v1/generations/images",
        headers=headers,
        json={"prompt": "studio portrait", "persona_id": created["id"]},
    )
    assert response.status_code == 202, response.text
    parameters = response.json()["parameters"]
    assert parameters["persona_id"] == created["id"]
    assert parameters["lora_id"] == lora

    # An explicit LoRA on the request always wins over the persona's.
    explicit = str(uuid4())
    response = client.post(
        "/api/v1/generations/images",
        headers=headers,
        json={"prompt": "studio portrait", "persona_id": created["id"], "lora_id": explicit},
    )
    assert response.status_code == 202
    assert response.json()["parameters"]["lora_id"] == explicit


def test_core_catalog_stays_private_to_characters() -> None:
    """Persistent personas are workspace data; the global catalog lists characters only."""

    headers = _token()
    _create_persona(headers, name="Private Persona")
    response = client.get("/api/v1/core/personas", headers=headers)
    assert response.status_code == 200
    names = {persona["name"] for persona in response.json()}
    # The seeded characters remain in the global catalog...
    assert "Petrick Martins" in names
    # ...and a tenant's persistent persona never leaks into it.
    assert "Private Persona" not in names


# ----------------------------------------------------------------- repository


def test_repository_contract_directly() -> None:
    """The repository is the API the spec requires — exercised without HTTP."""

    from app.repositories import persona_repo, slugify

    headers = _token()
    created = _create_persona(headers, name="Repo Contract")
    assert slugify("Dup Persona!!") == "dup-persona"

    # find_by_id / find_by_slug (slug is the stable identifier, unique per ws)
    assert persona_repo.find_by_id(created["id"]).name == "Repo Contract"
    assert persona_repo.find_by_slug("repo-contract", persona_repo.find_by_id(created["id"]).workspace_id) is not None
    # Unknown ids and empty input resolve to None, never raise.
    assert persona_repo.find_by_id("") is None
    assert persona_repo.find_by_id(str(uuid4())) is None
    assert persona_repo.find_by_slug("", "workspace") is None
    assert persona_repo.find_by_slug("repo-contract", "some-other-workspace") is None

    # set_lora points (and clears) the trained LoRA without a revision bump.
    lora = str(uuid4())
    assert persona_repo.set_lora(created["id"], lora).lora_id == lora
    assert persona_repo.set_lora(created["id"], None).lora_id is None

    # Writes against unknown personas report absence instead of raising.
    assert persona_repo.update(str(uuid4()), {"name": "x"}) is None
    assert persona_repo.delete(str(uuid4())) is False
    assert persona_repo.attach_image(str(uuid4()), str(uuid4()), "face") is None
    assert persona_repo.replace_references(str(uuid4()), [str(uuid4())]) is False

    # The mapping the Core uses: identity approved, version follows revision.
    memory = persona_repo.to_memory(persona_repo.find_by_id(created["id"]))
    assert memory.persona_id == created["id"]
    assert memory.status.value == "approved"
    assert memory.version == 1


# ------------------------------------------------------------------ migration


@pytest.fixture()
def temp_database(monkeypatch, tmp_path):
    from app.core.config import settings

    db_file = tmp_path / "persona-migration.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{db_file}")
    return db_file


def _alembic_config() -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic"))
    return config


def test_migration_0002_creates_the_persona_tables(temp_database) -> None:
    command.upgrade(_alembic_config(), "head")
    engine = create_engine(f"sqlite:///{temp_database}", pool_pre_ping=True)
    try:
        tables = set(inspect(engine).get_table_names())
        for expected in ("personas", "persona_images", "persona_wardrobe", "persona_identity_revision"):
            assert expected in tables, f"{expected} missing after upgrade head"
        # A table-level UNIQUE constraint is reported by get_unique_constraints
        # (get_indexes only lists the standalone indexes).
        constraints = {c["name"]: c["column_names"] for c in inspect(engine).get_unique_constraints("personas")}
        assert constraints.get("uq_personas_workspace_slug") == ["workspace_id", "slug"]
        # Idempotent: a second run changes nothing.
        command.upgrade(_alembic_config(), "head")
        assert set(inspect(engine).get_table_names()) == tables
    finally:
        engine.dispose()


def test_migration_0002_downgrade_never_drops_data(temp_database) -> None:
    command.upgrade(_alembic_config(), "head")
    engine = create_engine(f"sqlite:///{temp_database}", pool_pre_ping=True)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO personas (id, workspace_id, name, slug, age, height, body_type, skin_tone, hair, beard, eyes, voice, default_style, revision, created_at, updated_at) "
                "VALUES ('1','2','A','a',1,1.0,'','','','','','','',1,'now','now')"
            )
        )
    engine.dispose()

    command.downgrade(_alembic_config(), "0001")
    engine = create_engine(f"sqlite:///{temp_database}", pool_pre_ping=True)
    try:
        assert "personas" in set(inspect(engine).get_table_names()), "persona data must survive a downgrade"
    finally:
        engine.dispose()
