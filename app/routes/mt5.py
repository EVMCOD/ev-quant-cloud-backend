from fastapi import APIRouter, Request, HTTPException
from app.storage.mem_store import STORE
import os

router = APIRouter(prefix="/mt5", tags=["MT5 Bridge"])

TOKEN = os.getenv("EV_TV_WEBHOOK_TOKEN", "")

@router.get("/pull")
async def pull_signal(request: Request, token: str = None):
    header_token = request.headers.get("X-EV-Token")

    # Accept token from header OR query param
    if header_token != TOKEN and token != TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")

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
