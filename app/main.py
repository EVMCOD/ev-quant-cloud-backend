from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.routes import admin, mt5, tv


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Create all tables on startup (idempotent: skips existing tables)
    from app.db.database import init_db
    init_db()
    yield


app = FastAPI(title="EV Quant Cloud", version="0.4.0", lifespan=lifespan)

app.include_router(tv.router)
app.include_router(mt5.router)
app.include_router(admin.router)


@app.get("/health")
def health():
    return {"status": "ok"}
