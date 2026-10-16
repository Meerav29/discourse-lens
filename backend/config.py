"""
All configuration, read once from the environment / .env file.

Import `settings` and read attributes at call time (not at import time) so
tests can monkeypatch them.
"""

from __future__ import annotations

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Search: brave (needs BRAVE_API_KEY) or searxng (self-hosted, needs SEARXNG_URL)
    search_provider: Literal["brave", "searxng"] = "brave"
    brave_api_key: str = ""
    searxng_url: str = ""
    max_articles: int = 120

    # Look up open-access copies of academic pages the crawler can't read (OpenAlex, Europe PMC)
    recover_academic: bool = True

    # Claude
    claude_backend: Literal["anthropic", "vertex"] = "anthropic"
    claude_model: str = "claude-sonnet-5-5"
    anthropic_api_key: str | None = None  # SDK also resolves ANTHROPIC_API_KEY itself
    google_cloud_project: str | None = None
    vertex_region: str = "global"
    vertex_claude_model: str = "claude-sonnet-5-5"

    # Embeddings
    # fastembed runs nomic-embed-text in-process; ollama serves the same model
    # (identical vectors, so maps move freely between the two). "local" is the
    # old name for ollama. openai vectors are a different size: maps made with
    # them can only be searched with openai.
    embedding_mode: Literal["fastembed", "ollama", "local", "openai"] = "fastembed"
    fastembed_cache: str = "./data/models"
    ollama_base_url: str = "http://localhost:11434"
    openai_api_key: str | None = None

    # Storage
    db_path: str = "./data/discourse.db"
    lance_path: str = "./data/vectors"

    # Tuning
    rag_top_k: int = 15
    # Thinking effort for chat answers: low answers sooner, medium reasons more.
    chat_effort: Literal["low", "medium", "high"] = "medium"

    # Built frontend served at / (cd frontend && npm run build)
    frontend_build: str = "./frontend/build"

    # Frontend dev server origin allowed by CORS
    cors_origins: list[str] = ["http://localhost:5173"]


settings = Settings()
