from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.core import is_mt5_token_allowed
from app.db.database import get_db
from app.db.models import Account, Delivery, Signal

router = APIRouter(prefix="/mt5", tags=["MT5 Bridge"])
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def _extract_raw_token(
    x_ev_token: Optional[str] = Header(default=None, alias="X-EV-Token"),
    x_mt5_token: Optional[str] = Header(default=None, alias="X-MT5-Token"),
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
    token: Optional[str] = Query(default=None),
) -> str:
    """
    Extract bearer token from multiple sources (priority order):
      1. X-EV-Token   (current / preferred)
      2. X-MT5-Token  (legacy EA header)
      3. Authorization: Bearer <token>
      4. ?token=      (query param fallback)
    """
    bearer: Optional[str] = None
    if authorization and authorization.lower().startswith("bearer "):
        bearer = authorization[7:].strip() or None

    raw = (x_ev_token or x_mt5_token or bearer or token or "").strip()
    return raw


def _auth_token(raw: str, db: Session) -> str:
    """
    Validate raw token. Two paths:
      1. EV_MT5_TOKENS env var  (fast, backward-compat)
      2. accounts table active=True  (DB-registered tokens)
    On failure: logs last-4 chars of token and raises 401.
    """
    if not raw:
        raise HTTPException(status_code=401, detail="Unauthorized")

    # Fast path: env-var allow-list (existing behaviour)
    if is_mt5_token_allowed(raw):
        return raw

    # DB fallback: tokens registered via admin API
    acc = db.query(Account).filter_by(token=raw, active=True).first()
    if acc:
        return raw

    tail = raw[-4:] if len(raw) >= 4 else raw
    log.debug("Unauthorized token …%s (len=%d)", tail, len(raw))
    raise HTTPException(status_code=401, detail="Unauthorized")


def _get_or_create_account(token: str, db: Session) -> Account:
    """
    Auto-upsert: any validated token gets a row in accounts.
    Preserves backward-compat with EV_MT5_TOKENS env-var tokens.
    """
    acc = db.query(Account).filter_by(token=token).first()
    if acc is None:
        acc = Account(token=token, active=True)
        db.add(acc)
        db.commit()
        db.refresh(acc)
    elif not acc.active:
        raise HTTPException(status_code=403, detail="Account is inactive")
    return acc


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/pull")
def pull_signal(
    raw: str = Depends(_extract_raw_token),
    db: Session = Depends(get_db),
):
    """
    Pull the next PENDING delivery for this account.

    Uses SELECT … FOR UPDATE SKIP LOCKED so concurrent pulls never race on
    the same delivery row.  Transitions delivery: PENDING → LEASED.
    Payload shape is unchanged from the previous version.

    Auth accepted via (in priority order):
      X-EV-Token header  |  X-MT5-Token header  |  Authorization: Bearer  |  ?token=
    """
    token = _auth_token(raw, db)
    account = _get_or_create_account(token, db)

    delivery: Optional[Delivery] = (
        db.query(Delivery)
        .join(Signal, Signal.id == Delivery.signal_id)
        .filter(
            Delivery.account_id == account.id,
            Delivery.status == "PENDING",
        )
        .order_by(Signal.created_at.asc())
        .with_for_update(skip_locked=True)
        .first()
    )

    if not delivery:
        return {"signal": None}

    # Lease it
    delivery.status = "LEASED"
    delivery.leased_at = datetime.now(timezone.utc)
    db.commit()

    s: Signal = delivery.signal
    # Payload shape is intentionally unchanged from the original pull endpoint.
    return {
        "signal": {
            "id": s.id,
            "strategy": s.strategy,
            "symbol": s.symbol,
            "action": s.action,
            "risk_percent": s.risk_percent,
            "sl_points": s.sl_points,
            "tp_points": s.tp_points,
        }
    }


@router.post("/ack")
async def ack(
    request: Request,
    raw: str = Depends(_extract_raw_token),
    db: Session = Depends(get_db),
):
    """
    Acknowledge execution of a leased signal.
    Updates the delivery for THIS account only (not global).
    Payload shape is unchanged from the original ack endpoint.

    Auth accepted via (in priority order):
      X-EV-Token header  |  X-MT5-Token header  |  Authorization: Bearer  |  ?token=
    """
    token = _auth_token(raw, db)
    account = _get_or_create_account(token, db)

    try:
        payload: Dict[str, Any] = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    signal_id = str(payload.get("id") or payload.get("signal_id") or "").strip()
    if not signal_id:
        raise HTTPException(status_code=400, detail="Missing id")

    status = str(payload.get("status") or "").upper().strip()
    ticket = payload.get("ticket", 0) or 0
    price = payload.get("price", payload.get("fill_price", 0.0)) or 0.0
    slippage = payload.get("slippage", None)
    reason = payload.get("reason", payload.get("reject_reason", "UNKNOWN")) or "UNKNOWN"
    retcode = payload.get("retcode", None)

    try:
        delivery: Optional[Delivery] = (
            db.query(Delivery)
            .filter_by(signal_id=signal_id, account_id=account.id)
            .first()
        )

        if delivery is None:
            return {"status": "ok", "updated": False}

        now = datetime.now(timezone.utc)

        if status == "FILLED":
            delivery.status = "FILLED"
            delivery.ticket = int(ticket)
            delivery.fill_price = float(price)
            delivery.slippage = float(slippage) if slippage is not None else None
            delivery.closed_at = now
            db.commit()
            return {"status": "ok", "updated": True}

        if status == "REJECTED":
            if retcode is not None:
                reason = f"{reason} (retcode={retcode})"
            delivery.status = "REJECTED"
            delivery.reject_reason = str(reason)
            delivery.closed_at = now
            db.commit()
            return {"status": "ok", "updated": True}

    except Exception:
        return {"status": "ok", "updated": False}

    return {"status": "ok", "updated": False}
