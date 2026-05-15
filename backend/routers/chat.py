import time

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from chat.provider_factory import get_provider
from chat.tool_executor import ToolExecutor
from core.logging import get_logger
from dependencies import get_analytics_service, get_chat_context_service
from schemas import ChatRequest
from services.analytics_service import AnalyticsService
from services.chat_context_service import ChatContextService

router = APIRouter()
logger = get_logger(__name__)


@router.get("/api/chat/insights")
def chat_insights_endpoint(
    analytics: AnalyticsService = Depends(get_analytics_service),
):
    """Return top 2 behavioral flags + disposition summary for the alert banner."""
    try:
        flags = analytics.get_behavioral_red_flags()
        disposition_summary = None
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
    system_prompt = chat_context.build()
    logger.info("Chat context ready  %.2fs  chars=%d", time.perf_counter() - t0, len(system_prompt))

    msgs = [{"role": m.role, "content": m.content} for m in request.messages]
    provider = get_provider(request.provider)
    executor = ToolExecutor(analytics)

    return StreamingResponse(
        provider.stream_with_tools(msgs, system_prompt, executor, provider_name=request.provider),
        media_type="application/x-ndjson",
    )
