"""
Shared Claude client factory.

Supports two backends, selected by the CLAUDE_BACKEND env var:
  anthropic (default) — Direct Anthropic API, authenticated via ANTHROPIC_API_KEY
  vertex              — Google Cloud Vertex AI, authenticated via Application Default Credentials

Vertex AI setup:
  1. pip install anthropic[vertex]  (adds google-auth)
  2. gcloud auth application-default login
  3. Set GOOGLE_CLOUD_PROJECT and VERTEX_REGION in .env
"""

from __future__ import annotations

import os

CLAUDE_BACKEND = os.getenv("CLAUDE_BACKEND", "anthropic")

# Model IDs differ between backends — Vertex uses <name>@<date> format.
_ANTHROPIC_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
_VERTEX_MODEL = os.getenv("VERTEX_CLAUDE_MODEL", "claude-sonnet-4-0@20250514")


def get_client():
    """Return an Anthropic-compatible messages client for the configured backend."""
    if CLAUDE_BACKEND == "vertex":
        from anthropic import AnthropicVertex  # requires anthropic[vertex]
        return AnthropicVertex(
            project_id=os.environ["GOOGLE_CLOUD_PROJECT"],
            region=os.getenv("VERTEX_REGION", "us-east5"),
        )
    from anthropic import Anthropic
    return Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


def get_model() -> str:
    """Return the correct model ID string for the configured backend."""
    return _VERTEX_MODEL if CLAUDE_BACKEND == "vertex" else _ANTHROPIC_MODEL
