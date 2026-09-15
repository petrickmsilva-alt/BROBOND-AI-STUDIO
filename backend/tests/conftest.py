from pathlib import Path
import sys


# Keep tests runnable from the repository root and from backend/.
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def unlimited_rate_limit(monkeypatch):
    """PR002: the auth rate limiter is on in the application, but the test
    suite registers and logs in users constantly — a per-IP budget would turn
    unrelated tests red after the first few. The limiter itself is covered
    where it belongs, by the security tests, which set their own budget.
    """

    from app.core.config import settings

    monkeypatch.setattr(settings, "rate_limit_auth_per_minute", 0)
