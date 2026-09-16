"""PR009 — retry engine with explicit states (ETAPA 3).

Every failure is classified before the engine decides anything:

    retryable   transient error — try again after backoff
    timeout     the provider missed its deadline — treated as retryable,
                recorded with its own state so telemetry can tell them apart
    fatal       retrying cannot change the outcome (unsupported operation,
                invalid spec) — the engine stops immediately and re-raises
    backoff     not an error state: the wait inserted between attempts

Hard product invariant: **at most 3 attempts**. The delay between attempts
grows geometrically (``base * factor ** (attempt - 1)``) capped at
``max_delay_seconds``. The sleeper is injectable so tests never actually wait.
"""
from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, TypeVar

from ..core.config import settings
from .base_provider import (
    ProviderError,
    ProviderNotFound,
    ProviderTimeoutError,
    ProviderUnavailable,
    ProviderUnsupported,
)

#: Hard product invariant — never more than three attempts.
MAX_ATTEMPTS = 3

DEFAULT_BASE_DELAY_SECONDS = 0.25
DEFAULT_BACKOFF_FACTOR = 2.0
DEFAULT_MAX_DELAY_SECONDS = 5.0

T = TypeVar("T")


class RetryState(str, Enum):
    """The four states the PR009 retry engine reasons in."""

    RETRYABLE = "retryable"
    FATAL = "fatal"
    TIMEOUT = "timeout"
    BACKOFF = "backoff"


#: Errors that can never succeed on retry. An unsupported operation or an
#: invalid spec is a routing/contract problem, not a transient one — masking it
#: with retries would burn the attempt budget to produce the same failure.
FATAL_ERROR_TYPES: tuple[type[BaseException], ...] = (
    ProviderUnsupported,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
)




@dataclass(frozen=True)
class RetryDecision:
    """One step of the retry state machine, readable by telemetry and tests."""

    state: RetryState
    attempt: int
    max_attempts: int
    delay_seconds: float
    reason: str

    @property
    def is_last_attempt(self) -> bool:
        return self.attempt >= self.max_attempts

    def to_dict(self) -> dict[str, object]:
        return {
            "state": self.state.value,
            "attempt": self.attempt,
            "max_attempts": self.max_attempts,
            "delay_seconds": self.delay_seconds,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class RetryOutcome:
    """What the engine produced for one ``attempt`` call."""

    success: bool
    result: Any
    error: BaseException | None
    attempts: int
    decisions: tuple[RetryDecision, ...] = field(default_factory=tuple)

    @property
    def final_state(self) -> RetryState | None:
        """State of the last error-driven decision (None when clean)."""

        for decision in reversed(self.decisions):
            if decision.state in (RetryState.RETRYABLE, RetryState.FATAL, RetryState.TIMEOUT):
                return decision.state
        return None


class RetryPolicy:
    """Classification + backoff arithmetic, with no execution inside it."""

    def __init__(
        self,
        *,
        max_attempts: int = MAX_ATTEMPTS,
        base_delay_seconds: float | None = None,
        backoff_factor: float = DEFAULT_BACKOFF_FACTOR,
        max_delay_seconds: float = DEFAULT_MAX_DELAY_SECONDS,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if max_attempts > MAX_ATTEMPTS:
            # The 3-attempt ceiling is a product invariant, not a knob.
            raise ValueError(f"max_attempts cannot exceed {MAX_ATTEMPTS}")
        self.max_attempts = max_attempts
        self.base_delay_seconds = (
            settings.provider_retry_base_delay_seconds
            if base_delay_seconds is None
            else float(base_delay_seconds)
        )
        self.backoff_factor = float(backoff_factor)
        self.max_delay_seconds = float(max_delay_seconds)

    def classify(self, error: BaseException) -> RetryState:
        """Map an error onto a retry state. Never raises.

        Provider errors are judged before the generic fatal list on purpose:
        ``ProviderNotFound`` is also a ``KeyError``, but a missing provider is
        "unavailable right now" (retryable), not a contract bug.
        """

        if isinstance(error, (ProviderTimeoutError, TimeoutError, ConnectionError)):
            return RetryState.TIMEOUT
        if isinstance(error, ProviderUnsupported):
            return RetryState.FATAL
        if isinstance(error, (ProviderNotFound, ProviderUnavailable, ProviderError)):
            return RetryState.RETRYABLE
        if isinstance(error, FATAL_ERROR_TYPES):
            return RetryState.FATAL
        return RetryState.RETRYABLE

    def is_retryable(self, error: BaseException) -> bool:
        return self.classify(error) in (RetryState.RETRYABLE, RetryState.TIMEOUT)

    def delay_for(self, attempt: int) -> float:
        """Backoff before retrying after `attempt` (1-based)."""

        exponent = max(0, attempt - 1)
        delay = self.base_delay_seconds * (self.backoff_factor**exponent)
        return round(min(delay, self.max_delay_seconds), 6)


class RetryEngine:
    """Runs an operation under a RetryPolicy.

    ``sleeper`` is injectable so tests can observe backoff without waiting;
    ``on_decision`` receives every decision (error states and backoffs) for
    telemetry or logging.
    """

    def __init__(
        self,
        policy: RetryPolicy | None = None,
        *,
        sleeper: Callable[[float], None] = time.sleep,
        on_decision: Callable[[RetryDecision], None] | None = None,
    ) -> None:
        self.policy = policy or RetryPolicy()
        self._sleeper = sleeper
        self._on_decision = on_decision

    def attempt(self, operation: Callable[[], T]) -> RetryOutcome:
        """Run `operation` up to the attempt budget; classify every failure."""

        decisions: list[RetryDecision] = []
        error: BaseException | None = None
        for attempt in range(1, self.policy.max_attempts + 1):
            try:
                result = operation()
            except Exception as caught:  # noqa: BLE001 - the engine must classify every provider failure
                error = caught
                state = self.policy.classify(caught)
                decision = RetryDecision(
                    state=state,
                    attempt=attempt,
                    max_attempts=self.policy.max_attempts,
                    delay_seconds=self.policy.delay_for(attempt),
                    reason=str(caught) or caught.__class__.__name__,
                )
                decisions.append(decision)
                self._emit(decision)
                if state is RetryState.FATAL or attempt >= self.policy.max_attempts:
                    break
                backoff = RetryDecision(
                    state=RetryState.BACKOFF,
                    attempt=attempt,
                    max_attempts=self.policy.max_attempts,
                    delay_seconds=decision.delay_seconds,
                    reason=f"backoff before attempt {attempt + 1}",
                )
                decisions.append(backoff)
                self._emit(backoff)
                if decision.delay_seconds > 0:
                    self._sleeper(decision.delay_seconds)
                continue
            return RetryOutcome(
                success=True, result=result, error=None, attempts=attempt, decisions=tuple(decisions)
            )
        attempts_spent = sum(1 for decision in decisions if decision.state is not RetryState.BACKOFF)
        return RetryOutcome(
            success=False,
            result=None,
            error=error,
            attempts=attempts_spent,
            decisions=tuple(decisions),
        )

    def run(self, operation: Callable[[], T]) -> T:
        """Convenience wrapper: return the result or re-raise the last error."""

        outcome = self.attempt(operation)
        if outcome.success:
            return outcome.result
        raise outcome.error

    def _emit(self, decision: RetryDecision) -> None:
        if self._on_decision is not None:
            self._on_decision(decision)


def default_retry_engine() -> RetryEngine:
    """Engine wired to the deployment settings (used by the executor)."""

    return RetryEngine(RetryPolicy())
