from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    app_name: str = Field(default="FAQ Chatbot API")
    app_version: str = Field(default="0.1.0")
    faq_excel_path: Path = Field(default=BASE_DIR / "data" / "jakkawa_FAQ.xlsx")
    inquiry_review_excel_path: Path = Field(
        default=BASE_DIR / "data" / "Inquiry_review.xlsx"
    )
    support_email: str = Field(default="welcome@jakkawa.com")
    allowed_origins: list[str] = Field(default=["*"])
    semantic_threshold: float = Field(default=0.6)
    semantic_margin: float = Field(default=0.05)
    faq_match_threshold: float = Field(default=0.6)
    inquiry_match_threshold: float = Field(default=0.6)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


settings = Settings()
