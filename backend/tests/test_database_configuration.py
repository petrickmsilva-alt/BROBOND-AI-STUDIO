"""PR009.4 — database configuration hardening.

Covers the read priority (BROBOND_DATABASE_URL > DATABASE_URL > SQLite dev
fallback), the Render guard (never boot production on SQLite), the
`is_production_database()` utility and the startup banner.
"""
import pytest

from app.core.config import SQLITE_DEV_FALLBACK, Settings, _running_on_render


ENV_VARS = ("BROBOND_DATABASE_URL", "DATABASE_URL", "RENDER")


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch):
    """Each test starts from a bare environment: no database URLs and not on
    Render."""
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def make_settings() -> Settings:
    """Build Settings without `.env` interference (`_env_file=None`), so the
    tests exercise environment-variable priority in isolation."""
    return Settings(_env_file=None)


# ---------------------------------------------------------------- read priority


def test_brobond_database_url_is_read_first(monkeypatch):
    monkeypatch.setenv("BROBOND_DATABASE_URL", "postgresql+psycopg://one:pw@db-one:5432/brobond")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://two:pw@db-two:5432/brobond")
    settings = make_settings()
    assert settings.database_url == "postgresql+psycopg://one:pw@db-one:5432/brobond"


def test_database_url_is_read_when_brobond_variant_is_absent(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://two:pw@db-two:5432/brobond")
    settings = make_settings()
    assert settings.database_url == "postgresql+psycopg://two:pw@db-two:5432/brobond"


def test_database_url_from_paas_is_normalized_to_psycopg(monkeypatch):
    """Render injects `postgres://...`; the driverless scheme must be mapped
    to the bundled psycopg (v3) driver regardless of which variable carried it."""
    monkeypatch.setenv("DATABASE_URL", "postgres://render:pw@dpg-abc.oregon:5432/brobond")
    settings = make_settings()
    assert settings.database_url == "postgresql+psycopg://render:pw@dpg-abc.oregon:5432/brobond"


def test_local_fallback_is_sqlite_when_nothing_is_set():
    settings = make_settings()
    assert settings.database_url == SQLITE_DEV_FALLBACK
    assert settings.database_url.startswith("sqlite")


# ------------------------------------------------------------------ render guard


def test_render_without_database_url_raises_runtime_error(monkeypatch):
    monkeypatch.setenv("RENDER", "true")
    with pytest.raises(RuntimeError, match="Refusing to start on Render"):
        make_settings()


def test_render_with_explicit_sqlite_url_also_refuses(monkeypatch):
    """Even an explicitly configured SQLite URL is ephemeral inside a Render
    container — production never starts on SQLite, full stop."""
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.setenv("BROBOND_DATABASE_URL", "sqlite:///./anything.db")
    with pytest.raises(RuntimeError, match="Refusing to start on Render"):
        make_settings()


def test_render_with_postgres_boots_normally(monkeypatch):
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.setenv("BROBOND_DATABASE_URL", "postgres://render:pw@dpg-abc:5432/brobond")
    settings = make_settings()
    assert settings.database_url.startswith("postgresql+psycopg://")


def test_render_flag_spellings(monkeypatch):
    """`RENDER` truthiness is parsed defensively; falsy values do not arm the
    guard, every truthy spelling does."""
    for value in ("true", "1", "yes", "on", "TRUE", " True "):
        monkeypatch.setenv("RENDER", value)
        assert _running_on_render() is True
    for value in ("", "false", "0", "no", "off"):
        monkeypatch.setenv("RENDER", value)
        assert _running_on_render() is False
    monkeypatch.delenv("RENDER")
    assert _running_on_render() is False


# --------------------------------------------------------------------- utilities


def test_is_production_database_true_only_for_postgres(monkeypatch):
    monkeypatch.setenv("BROBOND_DATABASE_URL", "postgresql+psycopg://u:p@h:5432/db")
    assert make_settings().is_production_database() is True

    monkeypatch.delenv("BROBOND_DATABASE_URL")
    assert make_settings().is_production_database() is False


def test_startup_banner_reflects_database_engine(monkeypatch):
    monkeypatch.setenv("BROBOND_DATABASE_URL", "postgres://u:p@h:5432/db")
    assert make_settings().database_banner() == "🟢 PostgreSQL Connected"

    monkeypatch.delenv("BROBOND_DATABASE_URL")
    assert make_settings().database_banner() == "🔴 SQLite Development Mode"


# ------------------------------------------------- full module coverage (100%)
# The remaining Settings validators are exercised elsewhere in the suite; they
# are repeated here so this file alone proves `app.core.config` at 100%.


def test_short_jwt_secret_refuses_to_boot():
    with pytest.raises(ValueError, match="at least 32 bytes"):
        Settings(_env_file=None, jwt_secret="too-short")


def test_cors_origins_parse_trimmed_and_skip_empties():
    settings = Settings(_env_file=None, cors_origins=" https://a.example , ,https://b.example,")
    assert settings.cors_origin_list == ["https://a.example", "https://b.example"]
