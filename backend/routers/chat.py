import time
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth.dependencies import get_current_user
from chat.provider_factory import get_provider
from chat.tool_executor import ToolExecutor
from core.logging import get_logger
from database import get_db
from dependencies import get_analytics_service, get_chat_context_service
from models import ChatConversation, User
from schemas import ChatRequest
from services.analytics_service import AnalyticsService
from services.chat_context_service import ChatContextService

router = APIRouter()
logger = get_logger(__name__)

_MAX_CONVERSATIONS = 30


class ConversationUpsert(BaseModel):
    title: str
    messages: list[Any]
    provider: str = "gemini"


@router.get("/api/chat/conversations")
def list_conversations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = (
        db.query(ChatConversation)
        .filter(ChatConversation.user_id == current_user.id)
        .order_by(ChatConversation.updated_at.desc())
        .limit(_MAX_CONVERSATIONS)
        .all()
    )
    return [
        {
            "id": r.id,
            "title": r.title,
            "messages": r.messages,
            "provider": r.provider,
            "created_at": r.created_at.isoformat(),
            "updated_at": r.updated_at.isoformat(),
        }
        for r in rows
    ]


@router.put("/api/chat/conversations/{conv_id}", status_code=200)
def upsert_conversation(
    conv_id: str,
    body: ConversationUpsert,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = db.query(ChatConversation).filter(
        ChatConversation.id == conv_id,
        ChatConversation.user_id == current_user.id,
    ).first()

    now = datetime.now()
    if row:
        row.title = body.title
        row.messages = body.messages
        row.provider = body.provider
        row.updated_at = now
    else:
        row = ChatConversation(
            id=conv_id,
            user_id=current_user.id,
            title=body.title,
            messages=body.messages,
            provider=body.provider,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
    db.commit()
    return {"ok": True}


@router.delete("/api/chat/conversations/{conv_id}", status_code=204)
def delete_conversation(
    conv_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = db.query(ChatConversation).filter(
        ChatConversation.id == conv_id,
        ChatConversation.user_id == current_user.id,
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Conversation not found")
    db.delete(row)
    db.commit()


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
