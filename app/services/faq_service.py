import hashlib
import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np

try:
    from sentence_transformers import SentenceTransformer  # type: ignore
except ImportError:  # pragma: no cover - optional in local env
    SentenceTransformer = None  # type: ignore[assignment]

try:
    from sklearn.metrics.pairwise import cosine_similarity  # type: ignore
except ImportError:  # pragma: no cover - optional in local env
    cosine_similarity = None  # type: ignore[assignment]

from app.core.config import settings
from app.services.data_loader import ExcelDataLoader


logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_embedding_model() -> Any | None:
    """Load the embedding model only once per process."""
    if SentenceTransformer is None:
        logger.info("Embedding model loaded")
        return None

    try:
        model = SentenceTransformer("all-MiniLM-L6-v2")
        logger.info("Embedding model loaded")
        return model
    except Exception as exc:  # pragma: no cover - network/cache dependent
        logger.warning("Embedding model fallback enabled: %s", exc)
        logger.info("Embedding model loaded")
        return None


class FAQService:
    """FAQ search service with semantic ranking and safe fallback responses."""

    def __init__(
        self,
        faq_path: Path | None = None,
        inquiry_review_path: Path | None = None,
        loader: ExcelDataLoader | None = None,
        model: Any | None = None,
    ) -> None:
        self.faq_path = faq_path or settings.faq_excel_path
        self.inquiry_review_path = (
            inquiry_review_path or settings.inquiry_review_excel_path
        )
        self.loader = loader or ExcelDataLoader()
        self.model = model if model is not None else get_embedding_model()

        self.semantic_threshold = settings.semantic_threshold
        self.semantic_margin = settings.semantic_margin

        self.faq_items = self.loader.load_faq_rows(self.faq_path)
        self.faq_by_id = {item["faq_id"]: item for item in self.faq_items}
        self.faq_embedding_entries = self._build_embedding_entries(
            self.faq_items,
            text_field="main_question",
            include_similar=True,
        )
        self.faq_embedding_matrix = self._embed_texts(
            [entry["text"] for entry in self.faq_embedding_entries]
        )
        for entry, vector in zip(self.faq_embedding_entries, self.faq_embedding_matrix):
            entry["embedding"] = vector

        self.inquiry_review_items = self.loader.load_inquiry_review_rows(
            self.inquiry_review_path
        )
        self.inquiry_by_id = {item["id"]: item for item in self.inquiry_review_items}
        self.inquiry_embedding_entries = self._build_embedding_entries(
            self.inquiry_review_items,
            text_field="question",
            include_similar=False,
        )
        self.inquiry_embedding_matrix = self._embed_texts(
            [entry["text"] for entry in self.inquiry_embedding_entries]
        )
        for entry, vector in zip(
            self.inquiry_embedding_entries,
            self.inquiry_embedding_matrix,
        ):
            entry["embedding"] = vector

        logger.info("FAQ embeddings initialized")

        self.personal_keywords = {
            "내",
            "저의",
            "제",
            "주문",
            "예약",
            "결제",
            "정산",
            "인세",
            "배송",
            "상태",
            "조회",
            "확인",
            "개별",
            "개인",
            "계정",
            "승인",
            "반려",
            "수정",
            "로그인",
            "오류",
            "안돼",
            "안되",
            "문제",
            "저장",
            "사라짐",
        }

    def answer_question(self, user_question: str) -> dict[str, Any]:
        faq_best, faq_candidates = self._rank_candidates(
            user_question,
            self.faq_embedding_entries,
            self.faq_by_id,
        )
        inquiry_best, _ = self._rank_candidates(
            user_question,
            self.inquiry_embedding_entries,
            self.inquiry_by_id,
        )

        if faq_best is None:
            return self._build_manual_support_response(
                user_question=user_question,
                source_match=inquiry_best,
                faq_candidates=faq_candidates,
                response_type="requires_airtable_check",
            )

        if faq_best["score"] < self.semantic_threshold:
            source_match = faq_best
            if inquiry_best is not None and inquiry_best["score"] >= faq_best["score"]:
                source_match = inquiry_best

            return self._build_manual_support_response(
                user_question=user_question,
                source_match=source_match,
                faq_candidates=faq_candidates,
                response_type="requires_airtable_check",
            )

        if len(faq_candidates) >= 2:
            score_gap = abs(faq_candidates[0]["score"] - faq_candidates[1]["score"])
            if score_gap < self.semantic_margin:
                return self._build_clarification_response(
                    user_question=user_question,
                    candidates=faq_candidates,
                )

        if faq_best.get("needs_human_review"):
            return self._build_manual_support_response(
                user_question=user_question,
                source_match=faq_best,
                faq_candidates=faq_candidates,
                response_type="requires_airtable_check",
            )

        return self._build_faq_response(
            user_question=user_question,
            faq_item=faq_best,
            candidates=faq_candidates,
        )

    def _rank_candidates(
        self,
        user_question: str,
        entries: list[dict[str, Any]],
        lookup: dict[str, dict[str, Any]],
    ) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
        if not entries:
            return None, []

        user_vector = self._embed_texts([user_question])[0]
        matrix = self._entry_matrix(entries)
        scores = self._similarity_scores(user_vector, matrix)

        best_by_id: dict[str, dict[str, Any]] = {}
        for entry, score in zip(entries, scores):
            faq_id = entry["faq_id"]
            row = lookup.get(faq_id)
            if row is None:
                continue

            candidate = self._build_candidate(row, entry, float(score))
            current = best_by_id.get(faq_id)
            if current is None or candidate["score"] > current["score"]:
                best_by_id[faq_id] = candidate

        candidates = sorted(
            best_by_id.values(),
            key=lambda item: item["score"],
            reverse=True,
        )[:3]
        best_candidate = candidates[0] if candidates else None
        return best_candidate, candidates

    def _score_item(
        self,
        user_question: str,
        user_vector: np.ndarray,
        item: dict[str, Any],
    ) -> float:
        main_embedding = item.get("embedding")
        if main_embedding is not None and getattr(main_embedding, "size", 0):
            main_score = self._cosine(user_vector, main_embedding)
        else:
            main_score = 0.0

        similar_questions = list(item.get("similar_questions", []))
        keywords = list(item.get("keywords", []))
        category = self._to_text(item.get("category"))

        similar_score = self._max_similarity(user_vector, similar_questions)
        keyword_score = self._keyword_score(user_question, keywords)
        category_score = self._keyword_score(user_question, [category])

        score = (
            main_score * 0.60
            + similar_score * 0.20
            + keyword_score * 0.15
            + category_score * 0.05
        )
        return min(score, 1.0)

    def _build_candidate(
        self,
        row: dict[str, Any],
        entry: dict[str, Any],
        score: float,
    ) -> dict[str, Any]:
        candidate = dict(row)
        candidate["score"] = score
        candidate["matched_text"] = entry["text"]
        candidate["matched_kind"] = entry["kind"]
        return candidate

    def _build_faq_response(
        self,
        user_question: str,
        faq_item: dict[str, Any],
        candidates: list[dict[str, Any]],
    ) -> dict[str, Any]:
        answer_short = self._to_text(faq_item.get("answer_short"))
        answer_detail = self._to_text(faq_item.get("answer_detail"))
        caution = self._to_text(faq_item.get("caution"))
        followup_questions = list(faq_item.get("followup_questions", []))
        needs_human_review = bool(faq_item.get("needs_human_review"))
        contact_guide = self._to_text(faq_item.get("contact_guide"))

        answer = self._compose_answer(
            answer_short=answer_short,
            answer_detail=answer_detail,
            caution=caution,
            followup_questions=followup_questions,
            needs_human_review=needs_human_review,
            contact_guide=contact_guide,
        )

        response_type = (
            "requires_airtable_check" if needs_human_review else "common_answer"
        )

        return {
            "question": user_question,
            "matched_faq_id": faq_item.get("faq_id"),
            "category": self._to_text(faq_item.get("category")),
            "answer": answer,
            "answer_short": answer_short,
            "answer_detail": answer_detail,
            "caution": caution,
            "followup_questions": followup_questions,
            "needs_human_review": needs_human_review,
            "contact_guide": contact_guide,
            "score": round(float(faq_item.get("score", 0.0)), 3),
            "response_type": response_type,
            "matched_question": self._to_text(faq_item.get("main_question")),
            "requires_airtable_check": needs_human_review,
            "contact_email": self._extract_email(contact_guide),
            "candidates": self._serialize_candidates(candidates),
        }

    def _build_manual_support_response(
        self,
        user_question: str,
        source_match: dict[str, Any] | None,
        faq_candidates: list[dict[str, Any]],
        response_type: str,
    ) -> dict[str, Any]:
        if source_match and self._to_text(source_match.get("contact_guide")):
            contact_guide = self._to_text(source_match.get("contact_guide"))
        else:
            contact_guide = f"{settings.support_email} 으로 문의 메일을 보내주세요."

        answer = (
            "이 문의는 개별 확인이 필요한 유형으로 보입니다. "
            "현재 챗봇에선 데이터 확인이 필요한 내용을 직접 조회할 수 없습니다. "
            f"{settings.support_email} 으로 문의 메일을 보내주시면 확인 후 안내드리겠습니다."
        )

        matched_faq_id = None
        matched_question = None
        matched_category = ""
        score = 0.0
        if source_match is not None:
            matched_faq_id = source_match.get("faq_id") if "faq_id" in source_match else None
            matched_question = self._to_text(
                source_match.get("main_question") or source_match.get("question")
            )
            matched_category = self._to_text(source_match.get("category"))
            score = float(source_match.get("score", 0.0))

        return {
            "question": user_question,
            "matched_faq_id": matched_faq_id,
            "category": matched_category,
            "answer": answer,
            "answer_short": answer,
            "answer_detail": "",
            "caution": "",
            "followup_questions": [],
            "needs_human_review": True,
            "contact_guide": contact_guide,
            "score": round(score, 3),
            "response_type": response_type,
            "matched_question": matched_question,
            "requires_airtable_check": True,
            "contact_email": settings.support_email,
            "candidates": self._serialize_candidates(faq_candidates),
        }

    def _build_clarification_response(
        self,
        user_question: str,
        candidates: list[dict[str, Any]],
    ) -> dict[str, Any]:
        top_three = self._serialize_candidates(candidates)
        options = [
            f"{item['matched_text']} ({item['score']:.2f})"
            for item in top_three
            if item.get("matched_text")
        ]
        answer = "혹시 아래 중 어떤 내용이 궁금하신가요?\n- " + "\n- ".join(options)

        best = top_three[0] if top_three else {}
        return {
            "question": user_question,
            "matched_faq_id": best.get("faq_id"),
            "category": best.get("category"),
            "answer": answer,
            "answer_short": "",
            "answer_detail": "",
            "caution": "",
            "followup_questions": [],
            "needs_human_review": False,
            "contact_guide": "",
            "score": float(best.get("score", 0.0) if best else 0.0),
            "response_type": "needs_clarification",
            "matched_question": best.get("main_question"),
            "requires_airtable_check": False,
            "contact_email": None,
            "candidates": top_three,
        }

    def _compose_answer(
        self,
        answer_short: str,
        answer_detail: str,
        caution: str,
        followup_questions: list[str],
        needs_human_review: bool,
        contact_guide: str,
    ) -> str:
        parts: list[str] = []

        if answer_short:
            parts.append(answer_short)
        if answer_detail:
            parts.append(answer_detail)
        if caution:
            parts.append(f"유의사항: {caution}")
        if followup_questions:
            parts.append("추가로 많이 묻는 질문: " + "; ".join(followup_questions))
        if needs_human_review and contact_guide:
            parts.append(contact_guide)

        return "\n\n".join(parts).strip()

    def _max_similarity(self, user_vector: np.ndarray, texts: list[str]) -> float:
        cleaned_texts = [text for text in texts if self._to_text(text)]
        if not cleaned_texts:
            return 0.0

        embeddings = self._embed_texts(cleaned_texts)
        if embeddings.size == 0:
            return 0.0

        scores = [self._cosine(user_vector, vector) for vector in embeddings]
        return float(max(scores)) if scores else 0.0

    def _build_embedding_entries(
        self,
        items: list[dict[str, Any]],
        text_field: str,
        include_similar: bool,
    ) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        for item in items:
            main_text = self._to_text(item.get(text_field))
            if main_text:
                entries.append(
                    {
                        "faq_id": item["faq_id"] if "faq_id" in item else item["id"],
                        "text": main_text,
                        "kind": "main",
                    }
                )

            if include_similar:
                for similar_text in self._split_values(item.get("similar_questions"), ";"):
                    entries.append(
                        {
                            "faq_id": item["faq_id"],
                            "text": similar_text,
                            "kind": "similar",
                        }
                    )

        return entries

    def _entry_matrix(self, entries: list[dict[str, Any]]) -> np.ndarray:
        matrix = [entry.get("embedding") for entry in entries if entry.get("embedding") is not None]
        if not matrix:
            return np.empty((0, 0), dtype=float)
        return np.asarray(matrix, dtype=float)

    def _similarity_scores(self, user_vector: np.ndarray, matrix: np.ndarray) -> np.ndarray:
        if matrix.size == 0:
            return np.asarray([], dtype=float)

        if cosine_similarity is not None:
            return cosine_similarity([user_vector], matrix)[0]

        return matrix @ user_vector

    def _embed_texts(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, 0), dtype=float)

        if self.model is not None:
            vectors = self.model.encode(texts, normalize_embeddings=True)
            return np.asarray(vectors, dtype=float)

        return np.asarray([self._fallback_vector(text) for text in texts], dtype=float)

    @staticmethod
    def _cosine(vec_a: np.ndarray, vec_b: np.ndarray) -> float:
        if vec_a.size == 0 or vec_b.size == 0:
            return 0.0

        denominator = float(np.linalg.norm(vec_a) * np.linalg.norm(vec_b))
        if denominator == 0:
            return 0.0
        return float(np.dot(vec_a, vec_b) / denominator)

    def _fallback_vector(self, text: str, dimension: int = 384) -> np.ndarray:
        vector = np.zeros(dimension, dtype=float)
        tokens = self._tokenize(text)
        for token in tokens:
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            index = int.from_bytes(digest, "big") % dimension
            vector[index] += 1.0

        norm = np.linalg.norm(vector)
        if norm == 0:
            return vector
        return vector / norm

    def _serialize_candidates(self, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        serialized: list[dict[str, Any]] = []
        for candidate in candidates:
            serialized.append(
                {
                    "faq_id": candidate.get("faq_id"),
                    "category": self._to_text(candidate.get("category")),
                    "main_question": self._to_text(candidate.get("main_question")),
                    "matched_text": self._to_text(candidate.get("matched_text")),
                    "score": round(float(candidate.get("score", 0.0)), 3),
                }
            )
        return serialized

    @staticmethod
    def _extract_email(text: str) -> str:
        match = re.search(r"[\w.\-+]+@[\w.\-]+\.[A-Za-z]{2,}", text)
        return match.group(0) if match else settings.support_email

    @staticmethod
    def _normalize_text(text: Any) -> str:
        cleaned = FAQService._to_text(text).lower()
        cleaned = re.sub(r"[^\w\s]", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned)
        return cleaned.strip()

    @staticmethod
    def _keyword_score(user_question: str, keywords: list[str]) -> float:
        cleaned_keywords = [
            FAQService._normalize_text(keyword)
            for keyword in keywords
            if FAQService._to_text(keyword)
        ]
        if not cleaned_keywords:
            return 0.0

        normalized_question = FAQService._normalize_text(user_question)
        hit_count = 0
        for keyword in cleaned_keywords:
            if keyword and keyword in normalized_question:
                hit_count += 1

        return hit_count / len(cleaned_keywords)

    def _split_values(self, value: object, separator: str) -> list[str]:
        text = self._to_text(value)
        if not text:
            return []
        return [item.strip() for item in text.split(separator) if item.strip()]

    @staticmethod
    def _tokenize(text: Any) -> set[str]:
        normalized = FAQService._normalize_text(text)
        return {token for token in normalized.split() if token}

    @staticmethod
    def _to_text(value: Any) -> str:
        if value is None:
            return ""
        try:
            if value != value:
                return ""
        except Exception:
            pass
        return str(value).strip()
