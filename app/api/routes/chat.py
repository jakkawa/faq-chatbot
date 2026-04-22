from fastapi import APIRouter

from app.models.chat import ChatRequest, ChatResponse
from app.services.faq_service import FAQService


router = APIRouter(prefix="/chat", tags=["chat"])
faq_service = FAQService()


@router.post("/ask", response_model=ChatResponse)
def ask_question(payload: ChatRequest) -> ChatResponse:
    result = faq_service.answer_question(payload.question)
    return ChatResponse(**result)
