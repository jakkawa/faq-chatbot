from fastapi.testclient import TestClient

import app.api.routes.chat as chat_route
from app.main import app
from app.services.faq_service import FAQService


client = TestClient(app)


def test_health_check() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ask_question_returns_structured_common_answer() -> None:
    chat_route.faq_service = FAQService()

    response = client.post(
        "/api/v1/chat/ask",
        json={"question": "작가와는 어떤 좋은 서비스를 제공하고 있나요?"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["response_type"] == "common_answer"
    assert payload["matched_faq_id"] == "FAQ-001"
    assert payload["category"] == "서비스 일반"
    assert payload["score"] >= 0.6
    assert payload["answer_short"]
    assert payload["answer_detail"]
    assert isinstance(payload["followup_questions"], list)
    assert payload["requires_airtable_check"] is False
    assert isinstance(payload["candidates"], list)
    assert len(payload["candidates"]) <= 3
    assert payload["answer"].startswith(payload["answer_short"])
    assert "유의사항:" in payload["answer"]
    assert "추가로 많이 묻는 질문:" in payload["answer"]


def test_ask_question_returns_human_review_guidance() -> None:
    chat_route.faq_service = FAQService()

    response = client.post(
        "/api/v1/chat/ask",
        json={"question": "개인 작가가 아닌 출판사도 작가와를 이용할 수 있나요?"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["response_type"] == "requires_airtable_check"
    assert payload["needs_human_review"] is True
    assert payload["requires_airtable_check"] is True
    assert payload["contact_guide"]
    assert "welcome@jakkawa.com" in payload["contact_guide"]
    assert payload["contact_email"] == "welcome@jakkawa.com"
    assert payload["score"] >= 0.6
    assert isinstance(payload["candidates"], list)


def test_ask_question_with_low_similarity_requests_manual_check() -> None:
    chat_route.faq_service = FAQService()

    response = client.post(
        "/api/v1/chat/ask",
        json={"question": "주말 영화 추천해줘"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["response_type"] == "requires_airtable_check"
    assert payload["requires_airtable_check"] is True
    assert payload["score"] < 0.6
    assert "개별 확인이 필요한 유형" in payload["answer"]
    assert "welcome@jakkawa.com" in payload["answer"]
    assert isinstance(payload["candidates"], list)
