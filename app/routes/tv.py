from __future__ import annotations

import os
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import EV_TV_WEBHOOK_TOKEN
from app.db.database import get_db
from app.db.models import Account, Delivery, Group, Signal

router = APIRouter(prefix="/tv", tags=["TradingView"])


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class RiskModel(BaseModel):
    percent: float = Field(..., ge=0.0, le=10.0)


class SLTPModel(BaseModel):
    points: float = Field(..., gt=0)


class TVSignal(BaseModel):
    id: str
    strategy: str
    symbol: str
    action: str  # "BUY" / "SELL"
    risk: RiskModel
    sl: SLTPModel
    tp: SLTPModel

    # Auth (can also come via X-EV-Token header)
    token: Optional[str] = None

    # -----------------------------------------------------------------------
    # Routing fields – all optional, all defaulting to broadcast
    # Priority: broadcast > targets/target > groups/group > (default broadcast)
    # -----------------------------------------------------------------------
    broadcast: Optional[bool] = None          # True → send to every active account
    target: Optional[str] = None              # single account token
    targets: Optional[List[str]] = None       # list of account tokens
    group: Optional[str] = None               # single group name
    groups: Optional[List[str]] = None        # list of group names


# ---------------------------------------------------------------------------
# Routing resolution
# ---------------------------------------------------------------------------

def _resolve_account_ids(payload: TVSignal, db: Session) -> Optional[List[int]]:
    """
    Return the list of account_ids to create deliveries for,
    or None meaning "broadcast to every active account".

    Priority:
        broadcast=True  → None (all)
        target/targets  → those specific accounts
        group/groups    → union of members in those groups
        (nothing)       → None (all)

    Raises HTTP 400 on unknown/inactive targets or empty/unknown groups.
    """
    # 1. Explicit broadcast flag wins everything
    if payload.broadcast is True:
        return None

    account_ids: set[int] = set()

    # 2. Resolve token targets
    raw_tokens: set[str] = set()
    if payload.target:
        raw_tokens.add(payload.target.strip())
    if payload.targets:
        raw_tokens.update(t.strip() for t in payload.targets if t.strip())

    for tok in raw_tokens:
        acc = db.query(Account).filter_by(token=tok).first()
        if acc is None:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown account token: '{tok}'. Register it via POST /admin/accounts first.",
            )
        if not acc.active:
            raise HTTPException(
                status_code=400,
                detail=f"Account token '{tok}' is inactive.",
            )
        account_ids.add(acc.id)

    # 3. Resolve group names
    raw_groups: set[str] = set()
    if payload.group:
        raw_groups.add(payload.group.strip())
    if payload.groups:
        raw_groups.update(g.strip() for g in payload.groups if g.strip())

    for gname in raw_groups:
        grp = db.query(Group).filter_by(name=gname).first()
        if grp is None:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown group: '{gname}'. Create it via POST /admin/groups first.",
            )
        active_member_ids = [
            m.account_id
            for m in grp.members
            if m.account and m.account.active
        ]
        if not active_member_ids:
            raise HTTPException(
                status_code=400,
                detail=f"Group '{gname}' has no active members.",
            )
        account_ids.update(active_member_ids)

    # 4. Nothing specified → broadcast
    if not account_ids:
        return None

    return list(account_ids)


def _create_deliveries(signal: Signal, account_ids: Optional[List[int]], db: Session) -> int:
    """
    Insert Delivery rows. If account_ids is None → all active accounts.
    Returns count of deliveries created.
    """
    if account_ids is None:
        rows = db.query(Account.id).filter_by(active=True).all()
        account_ids = [r.id for r in rows]

    count = 0
    for aid in account_ids:
        d = Delivery(signal_id=signal.id, account_id=aid, status="PENDING")
        db.add(d)
        count += 1

    return count


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/webhook")
def receive_signal(
    payload: TVSignal,
    x_ev_token: Optional[str] = Header(default=None, alias="X-EV-Token"),
    db: Session = Depends(get_db),
):
    # --- auth ---
    expected = (EV_TV_WEBHOOK_TOKEN or "").strip()
    provided = (payload.token or "").strip() or (x_ev_token or "").strip()

    if not expected:
        raise HTTPException(status_code=500, detail="Server misconfigured: EV_TV_WEBHOOK_TOKEN missing")

    if provided != expected:
        raise HTTPException(
            status_code=401,
            detail=(
                "Invalid token "
                f"(got_len={len(provided)} "
                f"got_head4={provided[:4]} "
                f"got_tail4={provided[-4:] if len(provided) >= 4 else provided})"
            ),
        )

    # --- idempotency: already stored? ---
    if db.get(Signal, payload.id):
        return {"status": "accepted", "created": False, "signal_id": payload.id}

    # --- routing resolution (may raise 400) ---
    account_ids = _resolve_account_ids(payload, db)
    is_broadcast = account_ids is None

    # --- persist signal ---
    sig = Signal(
        id=payload.id,
        strategy=payload.strategy,
        symbol=payload.symbol,
        action=payload.action,
        risk_percent=float(payload.risk.percent),
        sl_points=float(payload.sl.points),
        tp_points=float(payload.tp.points),
        is_broadcast=is_broadcast,
    )
    db.add(sig)
    db.flush()  # ensure sig.id is visible for FK in deliveries

    delivery_count = _create_deliveries(sig, account_ids, db)
    db.commit()

    return {
        "status": "accepted",
        "created": True,
        "signal_id": sig.id,
        "deliveries": delivery_count,
        "routing": "broadcast" if is_broadcast else "targeted",
    }


@router.get("/debug_token")
def debug_token():
    expected = (os.getenv("EV_TV_WEBHOOK_TOKEN", "") or "").strip()
    return {
        "expected_len": len(expected),
        "expected_head4": expected[:4],
        "expected_tail4": expected[-4:] if len(expected) >= 4 else expected,
    }
