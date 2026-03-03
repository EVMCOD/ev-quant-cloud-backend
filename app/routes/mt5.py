from fastapi import APIRouter, Header, HTTPException
from app.main import STORE, is_mt5_token_allowed

router = APIRouter(prefix="/mt5", tags=["MT5 Bridge"])

from fastapi import APIRouter, Header, HTTPException
from app.main import STORE, is_mt5_token_allowed

router = APIRouter(prefix="/mt5", tags=["MT5 Bridge"])

@router.get("/pull")
def pull_signal(x_ev_token: str | None = Header(default=None, alias="X-EV-Token")):
    if not x_ev_token:
        raise HTTPException(status_code=401, detail="Unauthorized")

    token = x_ev_token.strip()

    if not is_mt5_token_allowed(token):
        raise HTTPException(status_code=401, detail="Unauthorized")

    s = STORE.pull_next_for_token(token)

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
            "tp_points": s.tp_points,
            "seq": s.seq
        }
    }

@router.post("/ack")
def ack(payload: dict, x_ev_token: str | None = Header(default=None, alias="X-EV-Token")):
    if not x_ev_token or not is_mt5_token_allowed(x_ev_token):
        raise HTTPException(status_code=401, detail="Unauthorized")
    return {"status": "ok"}

