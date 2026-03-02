from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel, Field
import time

from app.core.config import EV_TV_WEBHOOK_TOKEN
from app.storage.mem_store import STORE, Signal

router = APIRouter(prefix="/tv", tags=["TradingView"])

class RiskModel(BaseModel):
    percent: float = Field(..., gt=0, le=10)

class SLTPModel(BaseModel):
    points: float = Field(..., gt=0)

class TVSignal(BaseModel):
    id: str
    strategy: str
    symbol: str
    action: str
    risk: RiskModel
    sl: SLTPModel
    tp: SLTPModel

@router.post("/webhook")
def receive_signal(payload: TVSignal, x_ev_token: str | None = Header(default=None)):
    # Auth: token en header (recomendado)
    if x_ev_token != EV_TV_WEBHOOK_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid token")

    if payload.action not in ["BUY", "SELL", "CLOSE"]:
        raise HTTPException(status_code=400, detail="Invalid action")

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

    return {
        "status": "accepted",
        "created": created,
        "signal_id": payload.id
    }
