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

    # Search
    brave_api_key: str = ""
    max_articles: int = 120

    # Claude
    claude_backend: Literal["anthropic", "vertex"] = "anthropic"
    claude_model: str = "claude-sonnet-5-5"
    anthropic_api_key: str | None = None  # SDK also resolves ANTHROPIC_API_KEY itself
    google_cloud_project: str | None = None
    vertex_region: str = "global"
    vertex_claude_model: str = "claude-sonnet-5-5"

    # Embeddings
    embedding_mode: Literal["local", "openai"] = "local"
    ollama_base_url: str = "http://localhost:11434"
    openai_api_key: str | None = None

    # Storage
    db_path: str = "./data/discourse.db"
    lance_path: str = "./data/vectors"

    # Tuning
    umap_n_neighbors: int = 15
    kmeans_k: str = "auto"  # "auto" | integer string
    rag_top_k: int = 15
    # Thinking effort for chat answers: low answers sooner, medium reasons more.
    chat_effort: Literal["low", "medium", "high"] = "medium"

    # Built frontend served at / (cd frontend && npm run build)
    frontend_build: str = "./frontend/build"

    # Frontend dev server origin allowed by CORS
    cors_origins: list[str] = ["http://localhost:5173"]


settings = Settings()
