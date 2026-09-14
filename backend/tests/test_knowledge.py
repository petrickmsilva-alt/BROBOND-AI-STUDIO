from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_knowledge_base_is_seeded_and_searchable() -> None:
    response = client.get("/api/v1/knowledge", params={"category": "shot", "query": "SH001"})
    assert response.status_code == 200
    assert response.json()[0]["title"] == "Hero Walk"


def test_knowledge_base_contains_character_memory() -> None:
    response = client.get("/api/v1/knowledge", params={"category": "character"})
    assert response.status_code == 200
    assert any(entry["code"] == "CHAR_PETRICK" for entry in response.json())
