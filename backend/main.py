import os
import traceback

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from auth.router import router as auth_router
from core.logging import configure_logging, get_logger
from routers import alerts, index_trades, leveraged_etfs, portfolio, trades
from startup.lifespan import lifespan

configure_logging()
logger = get_logger(__name__)

app = FastAPI(title="Trading Portfolio Tracker", lifespan=lifespan)

_FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:3000")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[_FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.exception_handler(Exception)
async def unhandled_exception_handler(request, exc):
    logger.error(
        "Unhandled exception on %s %s:\n%s",
        request.method, request.url.path, traceback.format_exc(),
    )
    return JSONResponse(status_code=500, content={"detail": str(exc)})


app.include_router(auth_router)
app.include_router(trades.router)
app.include_router(index_trades.router)
app.include_router(leveraged_etfs.router)
app.include_router(portfolio.router)
app.include_router(alerts.router)
