"""PR002 — audit trail for critical actions (Bible §16).

Before this module the only log in the application was a `print` in the
database bootstrap, so a security review could not answer "who cancelled that
job, from where, when". `audit()` is called from the routes that perform
critical actions (authentication, job lifecycle, asset access, persona
identity changes) and writes an append-only row to `audit_log`.

Deliberately small:

* one call site, one row — the row is the unit of audit;
* the same action also emits a structured line on the `brobond.audit` logger,
  so a deployment without a queryable database still keeps a trail in its log
  stream;
* nothing here makes a decision. Deciding what is critical is the caller's
  job; this module only records.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from .auth import UserResponse
from .models import AuditLog, User

logger = logging.getLogger("brobond.audit")


def audit(
    db: Session,
    *,
    actor: User | UserResponse | None,
    action: str,
    resource_type: str = "",
    resource_id: str | None = None,
    workspace_id: str | None = None,
    detail: dict[str, Any] | None = None,
    request: Request | None = None,
) -> AuditLog:
    """Record one critical action.

    `actor` is None for anonymous or failed attempts (a failed login must be
    auditable even though there is no authenticated identity to attribute it
    to). `detail` is stored as JSON so callers never have to string-format
    facts the review will want to filter on.
    """

    entry = AuditLog(
        actor_id=actor.id if actor else None,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        workspace_id=workspace_id,
        detail=json.dumps(detail, ensure_ascii=False) if detail is not None else None,
        ip=request.client.host if request is not None and request.client else None,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)

    logger.info(
        json.dumps(
            {
                "audit": True,
                "action": action,
                "actor_id": entry.actor_id,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "workspace_id": workspace_id,
                "ip": entry.ip,
                "at": entry.created_at.isoformat() if entry.created_at else None,
            },
            ensure_ascii=False,
        )
    )
    return entry
