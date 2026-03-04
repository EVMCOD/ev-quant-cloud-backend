from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel, Field
import time

from app.core.config import EV_TV_WEBHOOK_TOKEN
from app.storage.mem_store import STORE, Signal

router = APIRouter(prefix="/tv", tags=["TradingView"])


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
    token: str | None = None  # <-- IMPORTANTE: token puede venir en el body


@router.post("/webhook")
def receive_signal(
    payload: TVSignal,
    x_ev_token: str | None = Header(default=None, alias="X-EV-Token"),
):
    # TradingView normalmente NO manda headers custom.
    # Por eso aceptamos token por header o por body.
    provided = (x_ev_token or payload.token or "").strip()
    expected = (EV_TV_WEBHOOK_TOKEN or "").strip()

    if not expected:
        raise HTTPException(status_code=500, detail="Server misconfigured: EV_TV_WEBHOOK_TOKEN missing")

    if provided != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")

    s = Signal(
        id=payload.id,
        strategy=payload.strategy,
        symbol=payload.symbol,
        action=payload.action,
        risk_percent=float(payload.risk.percent),
        sl_points=float(payload.sl.points),
        tp_points=float(payload.tp.points),
        created_at=time.time(),
    )
    created = STORE.add(s)

    return {"status": "accepted", "created": created, "signal_id": s.id}
import os
from fastapi import APIRouter

@router.get("/debug_token")
def debug_token():
    expected = (os.getenv("EV_TV_WEBHOOK_TOKEN", "") or "").strip()
    return {
        "expected_len": len(expected),
        "expected_head4": expected[:4],
        "expected_tail4": expected[-4:] if len(expected) >= 4 else expected,
    }