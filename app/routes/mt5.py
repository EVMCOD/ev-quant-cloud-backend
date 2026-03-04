from fastapi import APIRouter, Header, HTTPException
from app.storage.mem_store import STORE
from app.core import is_mt5_token_allowed

router = APIRouter(prefix="/mt5", tags=["MT5 Bridge"])


@router.get("/pull")
def pull_signal(x_ev_token: str | None = Header(default=None, alias="X-EV-Token")):
    token = (x_ev_token or "").strip()
    if not token or not is_mt5_token_allowed(token):
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
        }
    }


@router.post("/ack")
def ack(payload: dict, x_ev_token: str | None = Header(default=None, alias="X-EV-Token")):
    token = (x_ev_token or "").strip()
    if not token or not is_mt5_token_allowed(token):
        raise HTTPException(status_code=401, detail="Unauthorized")

    signal_id = str(payload.get("id") or payload.get("signal_id") or "").strip()
    if not signal_id:
        raise HTTPException(status_code=400, detail="Missing id")

    status = str(payload.get("status") or "").upper().strip()

    if status == "FILLED":
        ok = STORE.ack_filled_for_token(
            token=token,
            signal_id=signal_id,
            ticket=int(payload.get("ticket", 0)),
            price=float(payload.get("price", 0.0)),
            slippage=payload.get("slippage", None),
        )
        return {"ok": bool(ok)}

    if status == "REJECTED":
        ok = STORE.ack_rejected_for_token(
            token=token,
            signal_id=signal_id,
            reason=str(payload.get("reason", "UNKNOWN")),
        )
        return {"ok": bool(ok)}

    return {"ok": True}