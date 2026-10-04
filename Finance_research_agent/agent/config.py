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
