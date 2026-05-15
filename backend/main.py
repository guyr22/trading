import traceback

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from core.logging import configure_logging, get_logger
from routers import chat, index_trades, leveraged_etfs, portfolio, trades
from startup.lifespan import lifespan

configure_logging()
logger = get_logger(__name__)

app = FastAPI(title="Trading Portfolio Tracker", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request, exc):
    logger.error(
        "Unhandled exception on %s %s:\n%s",
        request.method, request.url.path, traceback.format_exc(),
    )
    return JSONResponse(status_code=500, content={"detail": str(exc)})


app.include_router(trades.router)
app.include_router(index_trades.router)
app.include_router(leveraged_etfs.router)
app.include_router(portfolio.router)
app.include_router(chat.router)
