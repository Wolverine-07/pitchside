"""Which model the agents talk to.

PITCHSIDE_PROVIDER picks one:
  foundry       Microsoft Foundry project endpoint (Entra ID auth)
  azure_openai  Azure OpenAI / Foundry resource endpoint with an API key
  ollama        a local model through Ollama's OpenAI-compatible API
  templates     no model at all; every line comes from verified templates
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass
class ModelConfig:
    provider: str
    model: str | None
    endpoint: str | None

    @property
    def offline(self) -> bool:
        return self.provider == "templates"


def config() -> ModelConfig:
    provider = os.getenv("PITCHSIDE_PROVIDER", "templates").lower()
    return ModelConfig(
        provider=provider,
        model=os.getenv("PITCHSIDE_MODEL") or os.getenv("AZURE_OPENAI_DEPLOYMENT"),
        endpoint=os.getenv("FOUNDRY_PROJECT_ENDPOINT") or os.getenv("AZURE_OPENAI_ENDPOINT"),
    )


def chat_client(cfg: ModelConfig | None = None):
    """Return an Agent Framework chat client, or None when running templates-only."""
    cfg = cfg or config()
    if cfg.provider == "templates":
        return None
    if cfg.provider == "foundry":
        from agent_framework.foundry import FoundryChatClient
        from azure.identity.aio import DefaultAzureCredential

        return FoundryChatClient(
            project_endpoint=cfg.endpoint, model=cfg.model, credential=DefaultAzureCredential()
        )
    if cfg.provider == "azure_openai":
        from agent_framework.openai import OpenAIChatCompletionClient

        return OpenAIChatCompletionClient(
            model=cfg.model,
            api_key=os.environ["AZURE_OPENAI_API_KEY"],
            azure_endpoint=cfg.endpoint,
            api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21"),
        )
    if cfg.provider == "ollama":
        from agent_framework.openai import OpenAIChatCompletionClient

        return OpenAIChatCompletionClient(
            model=cfg.model or "phi4-mini",
            api_key="ollama",
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
        )
    raise ValueError(f"unknown PITCHSIDE_PROVIDER: {cfg.provider}")
