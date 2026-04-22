# FAQ Chatbot

FastAPI + pandas 기반 FAQ 질의응답 챗봇입니다.

현재는 `data/jakkawa_FAQ.xlsx`의 `Sheet2`를 우선 사용합니다.
기존 `/api/v1/chat/ask` 엔드포인트와 `answer` 필드는 유지해서 Softr 연결이 크게 깨지지 않도록 했습니다.

## 검색 방식

서버가 시작되면 `Sheet2`의 `대표질문`과 `유사질문들`을 임베딩해서 메모리에 보관합니다.

질문이 들어오면 다음 순서로 처리합니다.

1. 사용자 질문과 FAQ 임베딩의 코사인 유사도를 계산합니다.
2. FAQ별 상위 후보 3개를 뽑습니다.
3. `semantic_threshold` 미만이면 개별 확인 안내를 반환합니다.
4. 1위와 2위 점수 차이가 `semantic_margin` 미만이면 바로 답하지 않고 선택지를 보여줍니다.
5. 점수가 충분히 높으면 `answer_short`, `answer_detail`, `caution`, `followup_questions`, `contact_guide`를 조합해 답변합니다.

## 엑셀 구조

`data/jakkawa_FAQ.xlsx`

`Sheet2` 컬럼:

- `faq_id`
- `category`
- `대표질문`
- `유사질문들`
- `핵심키워드`
- `answer_short`
- `answer_detail`
- `caution`
- `followup_questions`
- `needs_human_review`
- `contact_guide`
- `updated_at`

규칙:

- `유사질문들`은 `;`로 여러 질문을 구분합니다.
- `핵심키워드`는 `,`로 여러 키워드를 구분합니다.
- `followup_questions`는 `;`로 여러 질문을 구분합니다.
- `needs_human_review`는 `Y` 또는 `N`입니다.
- 빈 셀은 안전하게 무시합니다.

## 응답 예시

```json
{
  "question": "작가와는 무슨 서비스인가요?",
  "matched_faq_id": "FAQ-001",
  "category": "서비스 일반",
  "answer": "작가와는 누구나 자신의 이야기를 전자책으로 만들 수 있도록 돕는 서비스입니다.\n\n원고만 준비하면 전자책 제작과 출판·유통을 진행할 수 있도록 지원합니다.\n\n유의사항: 구체적인 작업 범위는 서비스 유형에 따라 달라질 수 있습니다.\n\n추가로 많이 묻는 질문: 출간 절차는 어떻게 되나요?; 준비물은 무엇인가요?",
  "answer_short": "작가와는 누구나 자신의 이야기를 전자책으로 만들 수 있도록 돕는 서비스입니다.",
  "answer_detail": "원고만 준비하면 전자책 제작과 출판·유통을 진행할 수 있도록 지원합니다.",
  "caution": "구체적인 작업 범위는 서비스 유형에 따라 달라질 수 있습니다.",
  "followup_questions": [
    "출간 절차는 어떻게 되나요?",
    "준비물은 무엇인가요?"
  ],
  "needs_human_review": false,
  "contact_guide": "",
  "score": 0.87,
  "response_type": "common_answer",
  "matched_question": "작가와는 어떤 좋은 서비스를 제공하고 있나요?",
  "requires_airtable_check": false,
  "contact_email": null,
  "candidates": []
}
```

점수가 낮으면 다음처럼 개별 확인 안내가 나갑니다.

```json
{
  "answer": "이 문의는 개별 확인이 필요한 유형으로 보입니다. 현재 챗봇에선 데이터 확인이 필요한 내용을 직접 조회할 수 없습니다. welcome@jakkawa.com 으로 문의 메일을 보내주시면 확인 후 안내드리겠습니다.",
  "response_type": "requires_airtable_check"
}
```

점수 차이가 거의 없으면 선택지를 보여줍니다.

```json
{
  "response_type": "needs_clarification",
  "answer": "혹시 아래 중 어떤 내용이 궁금하신가요?\n- ...\n- ...",
  "candidates": [
    {
      "faq_id": "FAQ-001",
      "category": "서비스 일반",
      "main_question": "작가와는 어떤 좋은 서비스를 제공하고 있나요?",
      "matched_text": "작가와는 무슨 서비스인가요?",
      "score": 0.91
    }
  ]
}
```

## 필요한 패키지

이번 변경으로 추가된 라이브러리는 두 개입니다.

- `sentence-transformers`
- `scikit-learn`

## 임계값 조정

기본값은 다음과 같습니다.

- `semantic_threshold=0.6`
- `semantic_margin=0.05`

환경변수로 조절할 수 있습니다.

## 로컬 실행

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

확인 주소:

- `http://127.0.0.1:8000/docs`
- `http://127.0.0.1:8000/health`

## 로컬 테스트

```bash
.\.venv\Scripts\python.exe -m pytest tests --basetemp .pytest_tmp
```

## 주요 파일

- [app/main.py](C:/Users/leade/OneDrive/문서/dev2/Codex/faq-chatbot/app/main.py)
- [app/api/routes/chat.py](C:/Users/leade/OneDrive/문서/dev2/Codex/faq-chatbot/app/api/routes/chat.py)
- [app/services/data_loader.py](C:/Users/leade/OneDrive/문서/dev2/Codex/faq-chatbot/app/services/data_loader.py)
- [app/services/faq_service.py](C:/Users/leade/OneDrive/문서/dev2/Codex/faq-chatbot/app/services/faq_service.py)
- [app/models/chat.py](C:/Users/leade/OneDrive/문서/dev2/Codex/faq-chatbot/app/models/chat.py)
