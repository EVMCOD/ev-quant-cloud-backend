from fastapi import FastAPI
from app.routes import tv, mt5

app = FastAPI(title="EV Quant Cloud", version="0.3.0")

app.include_router(tv.router)
app.include_router(mt5.router)

@app.get("/health")
def health():
    return {"status": "ok"}
