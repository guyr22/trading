import base64
import time

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from auth.dependencies import get_current_user
from chat.provider_factory import get_provider
from chat.tool_executor import ToolExecutor
from core.logging import get_logger
from dependencies import get_analytics_service, get_chat_context_service, get_config_repo
from models import User
from repositories.config_repository import ConfigRepository
from schemas import AppConfigUpdate, ChatRequest, TechnicalChatRequest
from services.analytics_service import AnalyticsService
from services.chat_context_service import ChatContextService

router = APIRouter()
logger = get_logger(__name__)

_TA_PROMPT_KEY = "ta_system_prompt"
_TA_PROMPT_DEFAULT = (
    "You are an expert technical analyst. "
    "Analyze the provided chart setup and give a detailed assessment."
)


def _parse_image(data_url: str) -> tuple[str, bytes, str]:
    """Return (media_type, raw_bytes, b64_str)."""
    header, data = data_url.split(",", 1)
    media_type = header.split(";")[0].split(":")[1]
    raw = base64.b64decode(data)
    return media_type, raw, base64.b64encode(raw).decode()


@router.get("/api/chat/insights")
def chat_insights_endpoint(
    analytics: AnalyticsService = Depends(get_analytics_service),
):
    """Return top 2 behavioral flags + disposition summary for the alert banner."""
    try:
        flags = analytics.get_behavioral_red_flags()
        disposition_summary = None
        all_closed_count = 0
        try:
            disposition_raw = analytics.get_disposition_effect()
            all_closed_count = disposition_raw.get("total_closed_lots", 0)
            if all_closed_count >= 5 and "error" not in disposition_raw:
                disposition_summary = {
                    "hold_ratio": disposition_raw["hold_ratio"],
                    "avg_winner_hold_days": disposition_raw["avg_winner_hold_days"],
                    "avg_loser_hold_days": disposition_raw["avg_loser_hold_days"],
                    "interpretation": disposition_raw["interpretation"],
                }
        except Exception:
            disposition_summary = None
        return {
            "flags": flags[:2],
            "has_insights": len(flags) > 0,
            "disposition_summary": disposition_summary,
        }
    except Exception:
        return {"flags": [], "has_insights": False, "disposition_summary": None}


@router.post("/api/chat")
def chat_endpoint(
    request: ChatRequest,
    analytics: AnalyticsService = Depends(get_analytics_service),
    chat_context: ChatContextService = Depends(get_chat_context_service),
):
    logger.info("Chat request  provider=%s  messages=%d", request.provider, len(request.messages))

    t0 = time.perf_counter()
    logger.info("Building chat context...")
    system_prompt = chat_context.build()
    logger.info("Chat context ready  %.2fs  chars=%d", time.perf_counter() - t0, len(system_prompt))

    msgs = [{"role": m.role, "content": m.content} for m in request.messages]
    provider = get_provider(request.provider)
    executor = ToolExecutor(analytics)
    logger.info("Starting stream  provider=%s", request.provider)

    return StreamingResponse(
        provider.stream_with_tools(msgs, system_prompt, executor, provider_name=request.provider),
        media_type="application/x-ndjson",
    )


@router.get("/api/config/ta-prompt")
def get_ta_prompt(
    config_repo: ConfigRepository = Depends(get_config_repo),
    _user: User = Depends(get_current_user),
):
    config = config_repo.get(_TA_PROMPT_KEY)
    return {"value": config.value if config else ""}


@router.put("/api/config/ta-prompt")
def update_ta_prompt(
    update: AppConfigUpdate,
    config_repo: ConfigRepository = Depends(get_config_repo),
    _user: User = Depends(get_current_user),
):
    config_repo.set(_TA_PROMPT_KEY, update.value)
    logger.info("TA system prompt updated (%d chars)", len(update.value))
    return {"value": update.value}


@router.post("/api/chat/technical")
def technical_chat_endpoint(
    request: TechnicalChatRequest,
    _user: User = Depends(get_current_user),
):
    logger.info(
        "Technical chat  provider=%s  messages=%d  images=%d",
        request.provider, len(request.messages), len(request.images),
    )
    # system prompt is fetched inside to avoid DB dep on the endpoint signature
    # (config_repo is injected separately if needed; here we use a default)
    from database import SessionLocal
    from repositories.config_repository import ConfigRepository as CR
    with SessionLocal() as db:
        cfg = CR(db).get(_TA_PROMPT_KEY)
    system_prompt = cfg.value if (cfg and cfg.value) else _TA_PROMPT_DEFAULT

    msgs = [{"role": m.role, "content": m.content} for m in request.messages]
    images = [_parse_image(u) for u in request.images]
    provider = get_provider(request.provider)

    return StreamingResponse(
        provider.stream_technical(msgs, system_prompt, images, provider_name=request.provider),
        media_type="application/x-ndjson",
    )
