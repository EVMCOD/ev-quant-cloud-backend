from fastapi import FastAPI
from app.routes import tv, mt5

app = FastAPI(title="EV Quant Cloud", version="0.3.0")

app.include_router(tv.router)
app.include_router(mt5.router)

@app.get("/health")
def health():
    return {"status": "ok"}
import os

def _truthy(v: str) -> bool:
    return (v or "").strip().lower() in ("1", "true", "yes", "y", "on")

TV_WEBHOOK_TOKEN = os.getenv("EV_TV_WEBHOOK_TOKEN", "").strip()
MT5_TOKENS_RAW   = os.getenv("EV_MT5_TOKENS", "").strip()
ALLOW_ANY_MT5    = _truthy(os.getenv("EV_ALLOW_ANY_MT5_TOKEN", ""))

def _parse_tokens(raw: str) -> set[str]:
    # IMPORTANTE: quita espacios para que "token1, token2" funcione igual
    return {t.strip() for t in (raw or "").replace(";", ",").split(",") if t.strip()}

ALLOWED_MT5_TOKENS = _parse_tokens(MT5_TOKENS_RAW)

def is_mt5_token_allowed(token: str) -> bool:
    if ALLOW_ANY_MT5:
        return True
    return token.strip() in ALLOWED_MT5_TOKENS

