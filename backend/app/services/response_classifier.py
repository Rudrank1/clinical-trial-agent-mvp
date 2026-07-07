from __future__ import annotations

from typing import Any

from app.services.gemini_service import GeminiReplyDecision, interpret_delivery_reply


def classify_delivery_reply(
    response_text: str,
    *,
    issue_id: int | None = None,
    candidate: dict[str, Any] | None = None,
) -> GeminiReplyDecision:
    """Classify a site reply through Gemini for the Decision Node."""
    return interpret_delivery_reply(
        issue_id=issue_id or 0,
        reply_text=response_text,
        candidate=candidate or {},
    )
