"""PR009.4.1 — Database health guard.

Single responsibility: prove the configured database answers a query.

* open a connection
* execute ``SELECT 1``
* enforce a wall-clock timeout (5 seconds by default)
* close the connection

It never creates tables and never runs migrations — schema is Alembic's job
(`app.main._bootstrap_database`). The guard is deliberately engine-agnostic:
the check itself works against SQLite in development, but the failure message
names PostgreSQL because that is the only engine production is allowed to run
on (PR009.4, `Settings.refuse_sqlite_on_render`).
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError

from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

from .config import settings

#: The PR contract: a probe that cannot answer within 5 seconds is down.
DEFAULT_TIMEOUT_SECONDS = 5.0

#: The exact failure message required by PR009.4.1's startup contract.
UNAVAILABLE_MESSAGE = "PostgreSQL unavailable"


class DatabaseGuard:
    """Opens one throwaway connection, runs ``SELECT 1``, closes it.

    The query runs in a worker thread so the deadline is wall-clock and
    driver-independent: a TCP connect that hangs (firewalled host, half-open
    Postgres) is abandoned at ``timeout_seconds`` instead of blocking startup
    or a health probe indefinitely.
    """

    def __init__(self, database_url: str | None = None, timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS) -> None:
        #: `None` means "follow settings at call time" — the singleton below
        #: keeps working when tests monkeypatch `settings.database_url`.
        self._database_url = database_url
        self.timeout_seconds = timeout_seconds

    @property
    def database_url(self) -> str:
        return self._database_url or settings.database_url

    def provider(self) -> str:
        """Short engine name for health payloads: `postgresql` or `sqlite`."""
        return "postgresql" if self.database_url.startswith(("postgresql", "postgres")) else "sqlite"

    def _select_one(self) -> None:
        """The entire check: connect, ``SELECT 1``, close. Nothing else.

        ``NullPool`` plus ``dispose()`` guarantees no connection outlives the
        call — the guard must not hold state between probes.
        """

        engine = create_engine(self.database_url, poolclass=NullPool)
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        finally:
            engine.dispose()

    def verify(self) -> None:
        """Raise ``RuntimeError("PostgreSQL unavailable")`` unless the database answers.

        Called at startup before FastAPI accepts requests (see `app.main`).
        Any failure mode — refused connection, bad credentials, or a probe
        exceeding the timeout — collapses into the same RuntimeError so the
        caller has exactly one contract to handle.
        """

        pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="db-guard")
        try:
            future = pool.submit(self._select_one)
            try:
                future.result(timeout=self.timeout_seconds)
            except FutureTimeoutError:
                future.cancel()
                raise RuntimeError(UNAVAILABLE_MESSAGE) from None
            except Exception as exc:
                raise RuntimeError(UNAVAILABLE_MESSAGE) from exc
        finally:
            # Never wait for a hung connection attempt; the probe already has
            # its answer and the worker thread is abandoned.
            pool.shutdown(wait=False, cancel_futures=True)

    def ping(self) -> bool:
        """Boolean form of `verify()` for health and readiness payloads."""

        try:
            self.verify()
        except RuntimeError:
            return False
        return True


#: Process-wide instance used by startup, `/api/v1/health` and readiness.
database_guard = DatabaseGuard()
