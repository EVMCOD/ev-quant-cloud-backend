import os
from dotenv import load_dotenv

load_dotenv()

def must_env(name: str) -> str:
    v = os.getenv(name, "").strip()
    if not v:
        raise RuntimeError(f"Missing env var: {name}")
    return v

EV_TV_WEBHOOK_TOKEN = must_env("EV_TV_WEBHOOK_TOKEN")
