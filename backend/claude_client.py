"""
Shared Claude client.

Supports two backends, selected by CLAUDE_BACKEND:
  anthropic (default) — Direct Anthropic API, authenticated via ANTHROPIC_API_KEY
  vertex              — Google Cloud Vertex AI, authenticated via Application Default Credentials

Vertex AI setup:
  1. uv sync --extra vertex  (adds google-auth)
  2. gcloud auth application-default login
  3. Set GOOGLE_CLOUD_PROJECT and VERTEX_REGION in .env
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from backend.config import settings

Effort = Literal["low", "medium", "high"]


class ClaudeRefusal(RuntimeError):
    """Claude declined the request (stop_reason == 'refusal')."""


@lru_cache(maxsize=1)
def get_client():
    """Return an Anthropic-compatible messages client for the configured backend."""
    if settings.claude_backend == "vertex":
        from anthropic import AnthropicVertex  # requires anthropic[vertex]
        if not settings.google_cloud_project:
            raise RuntimeError("GOOGLE_CLOUD_PROJECT must be set when CLAUDE_BACKEND=vertex")
        return AnthropicVertex(
            project_id=settings.google_cloud_project,
            region=settings.vertex_region,
        )
    from anthropic import Anthropic
    return Anthropic(api_key=settings.anthropic_api_key)


def get_model() -> str:
    """Return the model ID for the configured backend."""
    if settings.claude_backend == "vertex":
        return settings.vertex_claude_model
    return settings.claude_model


def complete(
    prompt: str,
    *,
    system: str | None = None,
    max_tokens: int = 16000,
    effort: Effort = "medium",
) -> str:
    """
    Single-turn request; returns the concatenated text blocks.

    Current models think by default, so content[0] may be a thinking block —
    always collect the text blocks. On the Anthropic API, server-side fallback
    re-runs a refused request on a suitable model within the same call.
    """
    kwargs = dict(
        model=get_model(),
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
        output_config={"effort": effort},
    )
    if system:
        kwargs["system"] = system

    client = get_client()
    if settings.claude_backend == "anthropic":
        response = client.beta.messages.create(
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            **kwargs,
        )
    else:
        response = client.messages.create(**kwargs)

    if response.stop_reason == "refusal":
        category = response.stop_details.category if response.stop_details else None
        raise ClaudeRefusal(f"Claude declined the request (category: {category})")

    return "".join(b.text for b in response.content if b.type == "text").strip()
