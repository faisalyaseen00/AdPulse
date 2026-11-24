"""Central configuration, loaded from environment / .env."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = Path(__file__).resolve().parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    # Warehouse
    clickhouse_host: str = "localhost"
    clickhouse_port: int = 8123
    clickhouse_database: str = "adpulse"
    clickhouse_user: str = "adpulse"
    clickhouse_password: str = "adpulse"
    clickhouse_reader_user: str = "adpulse_reader"
    clickhouse_reader_password: str = "change-me-reader"
    clickhouse_secure: bool = False

    # Agent query limits
    agent_max_rows: int = 500
    agent_query_timeout_s: int = 30
    agent_max_repairs: int = 2

    # LLM
    llm_provider: str = "anthropic"  # anthropic | groq | openrouter
    anthropic_api_key: str = ""
    anthropic_base_url: str = "https://api.anthropic.com"
    anthropic_model: str = "claude-opus-5-5"
    anthropic_effort: str = "medium"
    anthropic_fallbacks: bool = True
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-120b"
    groq_base_url: str = "https://api.groq.com/openai/v1"
    openrouter_api_key: str = ""
    openrouter_model: str = "anthropic/claude-opus-5.5"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    # Reports
    slack_bot_token: str = ""
    slack_channel: str = "#marketing-reports"
    slack_webhook_url: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    report_email_from: str = ""
    report_email_to: str = ""
    app_base_url: str = "http://localhost:8501"

    # Decision rules
    target_roas: float = 2.0
    target_cac: float = 60.0
    min_spend_for_decision: float = 300.0

    # Data
    data_dir: Path = PROJECT_ROOT / "data"

    @property
    def demo_dir(self) -> Path:
        return self.data_dir / "demo"

    @property
    def llm_configured(self) -> bool:
        return bool({"openrouter": self.openrouter_api_key, "groq": self.groq_api_key}.get(
            self.llm_provider, self.anthropic_api_key))

    @property
    def llm_label(self) -> str:
        if self.llm_provider == "openrouter":
            return f"OpenRouter · {self.openrouter_model}"
        if self.llm_provider == "groq":
            return f"Groq · {self.groq_model}"
        return f"Claude · {self.anthropic_model}"

    @property
    def slack_configured(self) -> bool:
        return bool(self.slack_webhook_url or self.slack_bot_token)

    @property
    def email_configured(self) -> bool:
        return bool(self.smtp_host and self.report_email_to and self.report_email_from)


@lru_cache
def get_settings() -> Settings:
    return Settings()
