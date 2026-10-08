from pydantic_settings import BaseSettings
from pydantic import Field
from pathlib import Path
from enum import Enum


class LLMProvider(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    VLLM = "vllm"


class Settings(BaseSettings):
    llm_provider: LLMProvider = LLMProvider.OPENAI
    llm_model: str = "gpt-4o"
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    vllm_base_url: str = "http://0.0.0.0:9000/v1"
    fmp_api_key: str = ""
    finnhub_api_key: str = ""
    upload_dir: Path = Path("./upload")
    output_dir: Path = Path("./output")

    # ── India market (required for DCF, no defaults — fail loudly) ──────────
    in_risk_free_rate: float | None = None          # decimal, e.g. 0.073 → 7.3%  (10Y G-sec)
    in_equity_risk_premium: float | None = None     # decimal, e.g. 0.060 → 6.0%
    in_default_tax_rate: float = 0.2517
    in_terminal_growth_cap: float = 0.05
    in_max_financials_age_days: int = 456

    # ── Upload / feature flags ──────────────────────────────────────────────
    max_upload_files: int = 40
    max_upload_mb: int = 150
    max_pdf_pages: int = 400
    pipeline_timeout_s: int = 120
    ocr_enabled: bool = True
    allow_llm_classifier: bool = False
    allow_llm_extraction: bool = False
    unlisted_dlom: float = 0.20
    unlisted_capital_structure: str = "peer_median"
    verdict_gating_enabled: bool = True
    max_method_divergence: float = 0.50

    def create_model(self):
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider

        if self.llm_provider == LLMProvider.VLLM:
            return OpenAIChatModel(
                self.llm_model,
                provider=OpenAIProvider(
                    base_url=self.vllm_base_url,
                    api_key="not-needed",
                ),
            )
        elif self.llm_provider == LLMProvider.OPENAI:
            return OpenAIChatModel(self.llm_model)
        elif self.llm_provider == LLMProvider.ANTHROPIC:
            from pydantic_ai.models.anthropic import AnthropicModel
            return AnthropicModel(self.llm_model)
        else:
            raise ValueError(f"Unknown provider: {self.llm_provider}")

    model_config = {"env_prefix": "", "env_file": ".env", "extra": "ignore"}
