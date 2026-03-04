from fastapi import APIRouter, Header, HTTPException, Request
from typing import Any, Dict, Optional

from app.storage.mem_store import STORE
from app.core import is_mt5_token_allowed

router = APIRouter(prefix="/mt5", tags=["MT5 Bridge"])


def _auth_token(x_ev_token: Optional[str]) -> str:
    token = (x_ev_token or "").strip()
    if not token or not is_mt5_token_allowed(token):
        raise HTTPException(status_code=401, detail="Unauthorized")
    return token


@router.get("/pull")
def pull_signal(x_ev_token: str | None = Header(default=None, alias="X-EV-Token")):
    token = _auth_token(x_ev_token)

    # broadcast per token if available
    if hasattr(STORE, "pull_next_for_token"):
        s = STORE.pull_next_for_token(token)
    else:
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
            "tp_points": s.tp_points,
        }
    }


@router.post("/ack")
async def ack(
    request: Request,
    x_ev_token: str | None = Header(default=None, alias="X-EV-Token"),
):
    token = _auth_token(x_ev_token)

    try:
        payload: Dict[str, Any] = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    signal_id = str(payload.get("id") or payload.get("signal_id") or "").strip()
    if not signal_id:
        raise HTTPException(status_code=400, detail="Missing id")

    status = str(payload.get("status") or "").upper().strip()

    # normalize
    ticket = payload.get("ticket", 0) or 0
    price = payload.get("price", payload.get("fill_price", 0.0)) or 0.0
    slippage = payload.get("slippage", None)
    reason = payload.get("reason", payload.get("reject_reason", "UNKNOWN")) or "UNKNOWN"
    retcode = payload.get("retcode", None)

    # IMPORTANT: never crash on ack
    try:
        if status == "FILLED":
            if hasattr(STORE, "ack_filled_for_token"):
                ok = STORE.ack_filled_for_token(token, signal_id, int(ticket), float(price), slippage)
            else:
                ok = STORE.ack_filled(signal_id, int(ticket), float(price), slippage)
            return {"status": "ok", "updated": bool(ok)}

        if status == "REJECTED":
            if retcode is not None:
                reason = f"{reason} (retcode={retcode})"
            if hasattr(STORE, "ack_rejected_for_token"):
                ok = STORE.ack_rejected_for_token(token, signal_id, str(reason))
            else:
                ok = STORE.ack_rejected(signal_id, str(reason))
            return {"status": "ok", "updated": bool(ok)}
    except Exception:
        # swallow any store error, never 500
        return {"status": "ok", "updated": False}

    return {"status": "ok", "updated": False}