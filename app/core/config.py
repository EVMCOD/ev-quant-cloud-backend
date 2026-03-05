import os
from dotenv import load_dotenv

load_dotenv()


def must_env(name: str) -> str:
    v = os.getenv(name, "").strip()
    if not v:
        raise RuntimeError(f"Missing required env var: {name}")
    return v


EV_TV_WEBHOOK_TOKEN = must_env("EV_TV_WEBHOOK_TOKEN")

# Postgres connection string — REQUIRED. No fallback to localhost.
# Set DATABASE_URL in Render env vars (Internal DB URL or External + ?sslmode=require).
DATABASE_URL: str = must_env("DATABASE_URL")

# Admin token for /admin/* routes.
# Falls back to TV token so single-token setups work out of the box.
EV_ADMIN_TOKEN: str = os.getenv("EV_ADMIN_TOKEN", "").strip() or EV_TV_WEBHOOK_TOKEN
