from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _token() -> dict:
    """PR002: the knowledge base holds persona PII and answers only to a token."""

    import uuid

    response = client.post(
        "/api/v1/auth/register",
        json={"email": f"knowledge-{uuid.uuid4()}@example.com", "name": "Knowledge Test", "password": "strong-pass-123"},
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_knowledge_base_is_seeded_and_searchable() -> None:
    response = client.get("/api/v1/knowledge", headers=_token(), params={"category": "shot", "query": "SH001"})
    assert response.status_code == 200
    assert response.json()[0]["title"] == "Hero Walk"


def test_knowledge_base_contains_character_memory() -> None:
    response = client.get("/api/v1/knowledge", headers=_token(), params={"category": "character"})
    assert response.status_code == 200
    assert any(entry["code"] == "CHAR_PETRICK" for entry in response.json())
