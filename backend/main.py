"""
AlphaBase Web API 入口
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.deps import lifespan

app = FastAPI(title="AlphaBase API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

try:
    from backend.api import notebook, backtest, data, factors
    app.include_router(notebook.router, prefix="/api/notebook", tags=["notebook"])
    app.include_router(backtest.router, prefix="/api/backtest", tags=["backtest"])
    app.include_router(data.router, prefix="/api/data", tags=["data"])
    app.include_router(factors.router, prefix="/api/factors", tags=["factors"])
except ImportError as e:
    import logging
    logging.warning(f"Some API routers not yet registered (will be added in later tasks): {e}")


@app.get("/api/health")
def health():
    return {"status": "ok"}