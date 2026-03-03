import os

def _truthy(v: str | None) -> bool:
    if not v:
        return False
    return v.strip().lower() in ("1", "true", "yes", "y", "on")

def is_mt5_token_allowed(token: str) -> bool:
    token = (token or "").strip()
    if not token:
        return False

    # allow-any switch (for testing)
    if _truthy(os.getenv("EV_ALLOW_ANY_MT5_TOKEN")):
        return True

    raw = os.getenv("EV_MT5_TOKENS", "")
    allowed = [t.strip() for t in raw.split(",") if t.strip()]
    return token in allowed