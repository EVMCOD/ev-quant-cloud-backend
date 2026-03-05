from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import EV_ADMIN_TOKEN
from app.db.database import get_db
from app.db.models import Account, Group, GroupMember, Signal
from app.routes.tv import RiskModel, SLTPModel, TVSignal, _create_deliveries, _resolve_account_ids

router = APIRouter(prefix="/admin", tags=["Admin"])


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def _require_admin(x_ev_token: Optional[str] = Header(default=None, alias="X-EV-Token")) -> None:
    token = (x_ev_token or "").strip()
    if not token or token != EV_ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="Admin token required")


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class AccountIn(BaseModel):
    token: str
    name: Optional[str] = None
    active: bool = True


class AccountOut(BaseModel):
    id: int
    token: str
    name: Optional[str]
    active: bool

    model_config = {"from_attributes": True}


class GroupIn(BaseModel):
    name: str


class GroupOut(BaseModel):
    id: int
    name: str
    members: List[str] = []  # list of account tokens

    model_config = {"from_attributes": True}


class MemberIn(BaseModel):
    token: str  # account token to add/remove


# ---------------------------------------------------------------------------
# Account endpoints
# ---------------------------------------------------------------------------

@router.post("/accounts", response_model=AccountOut, status_code=201)
def create_account(
    body: AccountIn,
    _: None = Depends(_require_admin),
    db: Session = Depends(get_db),
):
    existing = db.query(Account).filter_by(token=body.token).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Account with token already exists (id={existing.id})")
    acc = Account(token=body.token, name=body.name, active=body.active)
    db.add(acc)
    db.commit()
    db.refresh(acc)
    return acc


@router.get("/accounts", response_model=List[AccountOut])
def list_accounts(
    _: None = Depends(_require_admin),
    db: Session = Depends(get_db),
):
    return db.query(Account).order_by(Account.id).all()


@router.patch("/accounts/{account_id}")
def update_account(
    account_id: int,
    body: AccountIn,
    _: None = Depends(_require_admin),
    db: Session = Depends(get_db),
):
    acc = db.get(Account, account_id)
    if not acc:
        raise HTTPException(status_code=404, detail="Account not found")
    acc.name = body.name
    acc.active = body.active
    db.commit()
    return {"id": acc.id, "token": acc.token, "name": acc.name, "active": acc.active}


# ---------------------------------------------------------------------------
# Group endpoints
# ---------------------------------------------------------------------------

def _group_out(g: Group) -> dict:
    return {
        "id": g.id,
        "name": g.name,
        "members": [m.account.token for m in g.members if m.account],
    }


@router.post("/groups", status_code=201)
def create_group(
    body: GroupIn,
    _: None = Depends(_require_admin),
    db: Session = Depends(get_db),
):
    if db.query(Group).filter_by(name=body.name).first():
        raise HTTPException(status_code=409, detail=f"Group '{body.name}' already exists")
    g = Group(name=body.name)
    db.add(g)
    db.commit()
    db.refresh(g)
    return _group_out(g)


@router.get("/groups")
def list_groups(
    _: None = Depends(_require_admin),
    db: Session = Depends(get_db),
):
    return [_group_out(g) for g in db.query(Group).order_by(Group.id).all()]


@router.get("/groups/{name}")
def get_group(
    name: str,
    _: None = Depends(_require_admin),
    db: Session = Depends(get_db),
):
    g = db.query(Group).filter_by(name=name).first()
    if not g:
        raise HTTPException(status_code=404, detail=f"Group '{name}' not found")
    return _group_out(g)


@router.post("/groups/{name}/members", status_code=201)
def add_member(
    name: str,
    body: MemberIn,
    _: None = Depends(_require_admin),
    db: Session = Depends(get_db),
):
    g = db.query(Group).filter_by(name=name).first()
    if not g:
        raise HTTPException(status_code=404, detail=f"Group '{name}' not found")
    acc = db.query(Account).filter_by(token=body.token).first()
    if not acc:
        raise HTTPException(status_code=404, detail=f"Account with token '{body.token}' not found")
    existing = db.query(GroupMember).filter_by(group_id=g.id, account_id=acc.id).first()
    if existing:
        raise HTTPException(status_code=409, detail="Account is already a member of this group")
    db.add(GroupMember(group_id=g.id, account_id=acc.id))
    db.commit()
    db.refresh(g)
    return _group_out(g)


@router.delete("/groups/{name}/members/{token}", status_code=200)
def remove_member(
    name: str,
    token: str,
    _: None = Depends(_require_admin),
    db: Session = Depends(get_db),
):
    g = db.query(Group).filter_by(name=name).first()
    if not g:
        raise HTTPException(status_code=404, detail=f"Group '{name}' not found")
    acc = db.query(Account).filter_by(token=token).first()
    if not acc:
        raise HTTPException(status_code=404, detail=f"Account with token '{token}' not found")
    m = db.query(GroupMember).filter_by(group_id=g.id, account_id=acc.id).first()
    if not m:
        raise HTTPException(status_code=404, detail="Account is not a member of this group")
    db.delete(m)
    db.commit()
    db.refresh(g)
    return _group_out(g)


@router.delete("/groups/{name}", status_code=200)
def delete_group(
    name: str,
    _: None = Depends(_require_admin),
    db: Session = Depends(get_db),
):
    g = db.query(Group).filter_by(name=name).first()
    if not g:
        raise HTTPException(status_code=404, detail=f"Group '{name}' not found")
    db.delete(g)
    db.commit()
    return {"deleted": name}


# ---------------------------------------------------------------------------
# Admin probe: send test signals without exposing EV_TV_WEBHOOK_TOKEN
# ---------------------------------------------------------------------------

def _ingest_signal(payload: TVSignal, db: Session) -> dict:
    """
    Shared ingestion logic (same as /tv/webhook but token auth already done).
    Returns a summary dict.
    """
    if db.get(Signal, payload.id):
        return {"signal_id": payload.id, "created": False, "deliveries": 0, "routing": "duplicate"}

    account_ids = _resolve_account_ids(payload, db)
    is_broadcast = account_ids is None

    sig = Signal(
        id=payload.id,
        strategy=payload.strategy,
        symbol=payload.symbol,
        action=payload.action,
        risk_percent=float(payload.risk.percent),
        sl_points=float(payload.sl.points),
        tp_points=float(payload.tp.points),
        is_broadcast=is_broadcast,
        created_at=datetime.now(timezone.utc),
    )
    db.add(sig)
    db.flush()

    count = _create_deliveries(sig, account_ids, db)
    db.commit()

    return {
        "signal_id": sig.id,
        "created": True,
        "deliveries": count,
        "routing": "broadcast" if is_broadcast else "targeted",
    }


@router.post("/tv/send_probe", status_code=200)
def send_probe(
    _: None = Depends(_require_admin),
    db: Session = Depends(get_db),
):
    """
    Ingest two hardcoded test signals without needing EV_TV_WEBHOOK_TOKEN.
    Protected by EV_ADMIN_TOKEN (X-EV-Token header).

    Signal 1 – targeted:  probe_tgt_01  XAUUSD BUY  → only tokenCuenta1
    Signal 2 – broadcast: probe_bc_01   EURUSD SELL → all active accounts
    """
    probe_target = TVSignal(
        id="probe_tgt_01",
        strategy="AdminProbe",
        symbol="XAUUSD",
        action="BUY",
        risk=RiskModel(percent=1.0),
        sl=SLTPModel(points=200),
        tp=SLTPModel(points=400),
        target="tokenCuenta1",
    )

    probe_broadcast = TVSignal(
        id="probe_bc_01",
        strategy="AdminProbe",
        symbol="EURUSD",
        action="SELL",
        risk=RiskModel(percent=1.0),
        sl=SLTPModel(points=100),
        tp=SLTPModel(points=200),
    )

    result_target = _ingest_signal(probe_target, db)
    result_broadcast = _ingest_signal(probe_broadcast, db)

    return {
        "ok": True,
        "probe_tgt_01": result_target,
        "probe_bc_01": result_broadcast,
    }
