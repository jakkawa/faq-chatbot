from typing import Any, Literal

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    question: str = Field(
        ...,
        min_length=1,
        examples=["작가와는 무슨 서비스인가요?"],
    )


class ChatResponse(BaseModel):
    question: str
    matched_faq_id: str | None = None
    category: str | None = None
    answer: str
    answer_short: str = ""
    answer_detail: str = ""
    caution: str = ""
    followup_questions: list[str] = Field(default_factory=list)
    needs_human_review: bool = False
    contact_guide: str = ""
    score: float = 0.0
    response_type: Literal[
        "common_answer",
        "requires_airtable_check",
        "requires_manual_review",
        "needs_clarification",
    ]
    matched_question: str | None = None
    requires_airtable_check: bool
    contact_email: str | None = None
    candidates: list[dict[str, Any]] = Field(default_factory=list)
