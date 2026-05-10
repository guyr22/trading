"""M5 — Suggested follow-up questions: system prompt instruction tests."""
from services.chat_context_service import FOLLOW_UP_INSTRUCTIONS


def test_follow_up_instructions_present_in_module() -> None:
    """FOLLOW_UP_INSTRUCTIONS constant must exist and be non-empty."""
    assert FOLLOW_UP_INSTRUCTIONS
    assert len(FOLLOW_UP_INSTRUCTIONS) > 0


def test_follow_up_instruction_limits_to_two_questions() -> None:
    """Instruction must explicitly cap questions at 2."""
    text = FOLLOW_UP_INSTRUCTIONS.lower()
    assert "2" in text or "two" in text, (
        "Instruction must explicitly limit to 2 follow-up questions"
    )
    # The word 'more' (as in 'never more') or 'fewer' should appear to signal the cap
    assert "never more" in text or "no more" in text or "exactly 2" in text or "never fewer, never more" in text


def test_follow_up_instruction_requires_data_specificity() -> None:
    """Instruction must require questions to reference specific data (number, ticker, metric)."""
    text = FOLLOW_UP_INSTRUCTIONS.lower()
    # Should mention specificity requirements
    assert any(
        phrase in text
        for phrase in ["specific number", "ticker", "metric", "actual portfolio"]
    ), "Instruction must require data-specific questions"


def test_follow_up_instruction_excludes_simple_lookups() -> None:
    """Instruction must say to skip the section for simple factual lookups."""
    text = FOLLOW_UP_INSTRUCTIONS.lower()
    assert any(
        phrase in text
        for phrase in ["simple factual", "factual lookup", "do not append", "only include it when"]
    ), "Instruction must tell AI to skip follow-ups for simple factual lookups"


def test_follow_up_instructions_in_system_prompt(monkeypatch) -> None:
    """The system prompt built by ChatContextService must contain the follow-up instructions."""
    from unittest.mock import MagicMock, patch
    from datetime import date

    # Patch date.today so the prompt is deterministic
    fixed_date = date(2026, 4, 23)

    with patch("services.chat_context_service.date") as mock_date:
        mock_date.today.return_value = fixed_date
        mock_date.side_effect = lambda *a, **kw: date(*a, **kw)

        # Build a minimal mock portfolio_service
        portfolio_service = MagicMock()
        summary = MagicMock()
        summary.total_market_value = 10000.0
        summary.total_unrealized_pnl = 500.0
        summary.total_realized_pnl = 200.0
        summary.positions = []
        portfolio_service.build_summary.return_value = summary

        # Minimal mock trade_repo
        trade_repo = MagicMock()
        trade_repo.get_count_and_max_id.return_value = (0, 0)
        trade_repo.get_excluding.return_value = []

        from services.chat_context_service import ChatContextService

        service = ChatContextService.__new__(ChatContextService)
        service._trade_repo = trade_repo
        service._portfolio_service = portfolio_service
        service._analytics_service = None

        prompt = service._build_context()

    assert "FOLLOW-UP QUESTIONS RULE" in prompt, (
        "System prompt must contain the follow-up questions instruction block"
    )
    assert "You might also ask:" in prompt, (
        "System prompt must include the 'You might also ask:' template text"
    )
