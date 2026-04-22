from pathlib import Path
from typing import Any

import pandas as pd


class ExcelDataLoader:
    """Read FAQ and inquiry rows from Excel and normalize them."""

    def load_faq_rows(self, excel_path: Path) -> list[dict[str, Any]]:
        excel_file = pd.ExcelFile(excel_path)
        sheet_name = self._pick_faq_sheet_name(excel_file.sheet_names)
        dataframe = pd.read_excel(excel_path, sheet_name=sheet_name)
        dataframe = dataframe.rename(columns=self._clean_column_name)

        if self._is_sheet2_format(dataframe.columns):
            return self._load_sheet2_rows(dataframe)
        return self._load_legacy_rows(dataframe)

    def load_inquiry_review_rows(self, excel_path: Path) -> list[dict[str, Any]]:
        dataframe = pd.read_excel(excel_path)
        dataframe = dataframe.rename(columns=self._clean_column_name)

        review_rows: list[dict[str, Any]] = []
        for index, row in dataframe.iterrows():
            inquiry_detail = self._to_text(row.get("Inquiry Detail"))
            inquiry_category = self._to_text(row.get("Inquiry Category"))
            reply_text = self._to_text(row.get("회신 내용"))

            if not inquiry_detail:
                continue

            review_rows.append(
                {
                    "id": str(index + 1),
                    "question": inquiry_detail,
                    "category": inquiry_category,
                    "answer": reply_text,
                }
            )

        return review_rows

    def _load_sheet2_rows(self, dataframe: pd.DataFrame) -> list[dict[str, Any]]:
        faq_rows: list[dict[str, Any]] = []
        for _, row in dataframe.iterrows():
            faq_id = self._to_text(row.get("faq_id"))
            main_question = self._to_text(row.get("대표질문"))
            similar_questions = self._split_values(row.get("유사질문들"), ";")
            keywords = self._split_values(row.get("핵심키워드"), ",")
            answer_short = self._to_text(row.get("answer_short"))
            answer_detail = self._to_text(row.get("answer_detail"))
            caution = self._to_text(row.get("caution"))
            followup_questions = self._split_values(
                row.get("followup_questions"), ";"
            )
            needs_human_review = self._parse_yes_no(row.get("needs_human_review"))
            contact_guide = self._to_text(row.get("contact_guide"))
            updated_at = row.get("updated_at")
            category = self._to_text(row.get("category"))

            if not faq_id or not main_question:
                continue

            faq_rows.append(
                {
                    "faq_id": faq_id,
                    "category": category,
                    "main_question": main_question,
                    "similar_questions": similar_questions,
                    "keywords": keywords,
                    "answer_short": answer_short,
                    "answer_detail": answer_detail,
                    "caution": caution,
                    "followup_questions": followup_questions,
                    "needs_human_review": needs_human_review,
                    "contact_guide": contact_guide,
                    "updated_at": updated_at,
                }
            )

        return faq_rows

    def _load_legacy_rows(self, dataframe: pd.DataFrame) -> list[dict[str, Any]]:
        faq_rows: list[dict[str, Any]] = []
        for index, row in dataframe.iterrows():
            question = self._to_text(row.get("질문"))
            answer = self._to_text(row.get("답변"))
            category = self._to_text(row.get("카테고리"))

            if not question or not answer:
                continue

            faq_rows.append(
                {
                    "faq_id": str(index + 1),
                    "category": category,
                    "main_question": question,
                    "similar_questions": [],
                    "keywords": [],
                    "answer_short": answer,
                    "answer_detail": "",
                    "caution": "",
                    "followup_questions": [],
                    "needs_human_review": False,
                    "contact_guide": "",
                    "updated_at": None,
                }
            )

        return faq_rows

    @staticmethod
    def _pick_faq_sheet_name(sheet_names: list[str]) -> str:
        if "Sheet2" in sheet_names:
            return "Sheet2"
        if len(sheet_names) > 1:
            return sheet_names[1]
        return sheet_names[0]

    @staticmethod
    def _is_sheet2_format(columns: pd.Index) -> bool:
        expected = {
            "faq_id",
            "category",
            "대표질문",
            "유사질문들",
            "핵심키워드",
            "answer_short",
            "answer_detail",
            "caution",
            "followup_questions",
            "needs_human_review",
            "contact_guide",
            "updated_at",
        }
        return expected.issubset(set(columns))

    @staticmethod
    def _clean_column_name(value: object) -> str:
        return str(value).strip() if value is not None else ""

    @staticmethod
    def _split_values(value: object, separator: str) -> list[str]:
        text = ExcelDataLoader._to_text(value)
        if not text:
            return []
        return [item.strip() for item in text.split(separator) if item.strip()]

    @staticmethod
    def _parse_yes_no(value: object) -> bool:
        text = ExcelDataLoader._to_text(value).upper()
        return text == "Y"

    @staticmethod
    def _to_text(value: object) -> str:
        if value is None or pd.isna(value):
            return ""
        return str(value).strip()
