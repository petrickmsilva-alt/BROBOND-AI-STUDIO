"""PR009 — provider execution telemetry (ETAPA 6).

Every execution that crosses the universal executor leaves one record:

    provider          who actually produced the asset
    requested_provider_id   who was asked (differs on fallback)
    latency_ms        wall-clock total for the execute() call
    queue_time_ms     time spent before the first provider attempt
    render_time_ms    time spent inside provider generation calls
    success           whether an asset was produced
    error_code        machine-readable failure class (None on success)

Records live in a bounded, thread-safe in-process store. When
``BROBOND_PROVIDER_TELEMETRY_LOG`` points at a file, each record is also
appended as one JSON line, so a deployment can keep history across restarts
without a database migration.
"""
from __future__ import annotations

import json
import threading
from collections import deque
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..core.config import settings

#: Bounded history: telemetry is diagnostic, not a ledger.
DEFAULT_HISTORY_LIMIT = 500

#: Machine-readable failure classes. A success carries ``None``.
ERROR_TIMEOUT = "timeout"
ERROR_UNAVAILABLE = "unavailable"
ERROR_UNSUPPORTED = "unsupported"
ERROR_GENERATION = "generation-error"
ERROR_NOT_REGISTERED = "not-registered"
ERROR_FATAL = "fatal"


def telemetry_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class ProviderTelemetryRecord:
    """One execution as the executor saw it."""

    provider_id: str
    requested_provider_id: str
    spec_id: str
    kind: str
    success: bool
    error_code: str | None
    latency_ms: float
    queue_time_ms: float
    render_time_ms: float
    attempts: int = 1
    fallback: bool = False
    fallback_reason: str | None = None
    job_id: str | None = None
    at: str = ""

    def __post_init__(self) -> None:
        if not self.at:
            object.__setattr__(self, "at", telemetry_timestamp())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class TelemetryStore:
    """Bounded, thread-safe telemetry history with an optional JSONL sink."""

    def __init__(self, *, limit: int = DEFAULT_HISTORY_LIMIT, log_path: str | Path | None = None) -> None:
        if limit < 1:
            raise ValueError("limit must be at least 1")
        self._records: deque[ProviderTelemetryRecord] = deque(maxlen=limit)
        self._lock = threading.Lock()
        self._log_path = Path(log_path) if log_path else None

    @property
    def log_path(self) -> Path | None:
        return self._log_path

    def record(self, entry: ProviderTelemetryRecord) -> ProviderTelemetryRecord:
        """Append a record (and persist it when a sink is configured)."""

        with self._lock:
            self._records.append(entry)
        if self._log_path is not None:
            self._append_jsonl(entry)
        return entry

    def recent(self, limit: int = 50) -> tuple[ProviderTelemetryRecord, ...]:
        """Newest-first records, at most `limit`."""

        if limit < 1:
            return ()
        with self._lock:
            items = list(self._records)
        return tuple(reversed(items[-limit:]))

    def clear(self) -> None:
        with self._lock:
            self._records.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._records)

    def _append_jsonl(self, entry: ProviderTelemetryRecord) -> None:
        try:
            self._log_path.parent.mkdir(parents=True, exist_ok=True)
            with self._log_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")
        except OSError:
            # Telemetry must never take a render down: the in-memory record
            # already happened, the sink is best-effort.
            pass


_default_store: TelemetryStore | None = None
_default_lock = threading.Lock()


def default_telemetry_store() -> TelemetryStore:
    """Process-wide store shared by the executor and the API routes.

    Built lazily so the `BROBOND_PROVIDER_TELEMETRY_LOG` setting is read once,
    at first use, not at import time.
    """

    global _default_store
    with _default_lock:
        if _default_store is None:
            log = settings.provider_telemetry_log.strip()
            _default_store = TelemetryStore(log_path=log or None)
        return _default_store


def reset_default_telemetry_store() -> None:
    """Test seam: drop the cached store so settings are re-read."""

    global _default_store
    with _default_lock:
        _default_store = None


def records_to_payloads(records: Iterable[ProviderTelemetryRecord]) -> list[dict[str, Any]]:
    return [record.to_dict() for record in records]
