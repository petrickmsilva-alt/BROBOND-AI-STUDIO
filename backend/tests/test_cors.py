"""Regression coverage for HOTFIX PR009.3 CORS communication."""

from fastapi.testclient import TestClient
import pytest

from app.core.config import Settings
from app.main import app


WEB_ORIGIN = "https://brobond-studio-web.onrender.com"
PREFLIGHT_HEADERS = {
    "Origin": WEB_ORIGIN,
    "Access-Control-Request-Method": "GET",
}


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/health",
        "/api/v1/assets",
        "/api/v1/personas",
    ],
)
def test_deployed_frontend_preflight_is_allowed(path: str) -> None:
    response = TestClient(app).options(path, headers=PREFLIGHT_HEADERS)

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == WEB_ORIGIN
    assert response.headers["access-control-allow-credentials"] == "true"
    assert "GET" in response.headers["access-control-allow-methods"]


def test_trace_header_is_exposed_to_deployed_frontend() -> None:
    response = TestClient(app).get("/api/v1/health", headers={"Origin": WEB_ORIGIN})

    assert response.status_code == 200
    assert response.headers["access-control-expose-headers"] == "x-brobond-trace"


def test_cors_origins_parser_trims_spaces_and_ignores_empty_values() -> None:
    settings = Settings(
        cors_origins=(
            " https://brobond-studio-web.onrender.com, "
            "http://localhost:3000, ,"
        )
    )

    assert settings.cors_origin_list == [
        "https://brobond-studio-web.onrender.com",
        "http://localhost:3000",
    ]
    assert "*" not in settings.cors_origin_list
