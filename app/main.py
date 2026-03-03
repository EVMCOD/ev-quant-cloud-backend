from fastapi import FastAPI
from app.routes import tv, mt5

app = FastAPI(title="EV Quant Cloud", version="0.3.0")

app.include_router(tv.router)
app.include_router(mt5.router)

@app.get("/health")
def health():
    return {"status": "ok"}
import os
from fastapi import Header

@app.get("/debug/env")
def debug_env():
    tv = os.getenv("EV_TV_WEBHOOK_TOKEN", "").strip()
    mt5 = os.getenv("EV_MT5_TOKENS", "").strip()
    allow_any = os.getenv("EV_ALLOW_ANY_MT5_TOKEN", "").strip()

    tokens = [t.strip() for t in mt5.split(",") if t.strip()]

    return {
        "has_EV_TV_WEBHOOK_TOKEN": bool(tv),
        "has_EV_MT5_TOKENS": bool(mt5),
        "EV_MT5_TOKENS_count": len(tokens),
        "EV_ALLOW_ANY_MT5_TOKEN": allow_any,
    }

@app.get("/debug/headers")
def debug_headers(x_ev_token: str | None = Header(default=None, alias="X-EV-Token")):
    tok = (x_ev_token or "").strip()
    return {
        "has_X_EV_Token": bool(tok),
        "token_len": len(tok),
    }
