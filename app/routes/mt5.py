from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.storage.mem_store import STORE

router = APIRouter(prefix="/mt5", tags=["MT5 Bridge"])

@router.get("/pull")
def pull_signal():
    s = STORE.pull_next()

    if not s:
        return {"signal": None}

    return {
        "signal": {
            "id": s.id,
            "strategy": s.strategy,
            "symbol": s.symbol,
            "action": s.action,
            "risk_percent": s.risk_percent,
            "sl_points": s.sl_points,
            "tp_points": s.tp_points
        }
    }

class AckPayload(BaseModel):
    id: str
    status: str          # FILLED / REJECTED
    ticket: int | None = None
    price: float | None = None
    slippage: float | None = None
    reason: str | None = None

@router.post("/ack")
def ack(payload: AckPayload):
    st = payload.status.upper()

    if st == "FILLED":
        if payload.ticket is None or payload.price is None:
            raise HTTPException(status_code=400, detail="FILLED requires ticket and price")
        ok = STORE.ack_filled(payload.id, payload.ticket, payload.price, payload.slippage)
        if not ok:
            raise HTTPException(status_code=404, detail="Signal not found")
        return {"ok": True}

    if st == "REJECTED":
        ok = STORE.ack_rejected(payload.id, payload.reason or "UNKNOWN")
        if not ok:
            raise HTTPException(status_code=404, detail="Signal not found")
        return {"ok": True}

    raise HTTPException(status_code=400, detail="Invalid status")
