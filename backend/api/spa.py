"""Serve the built frontend (frontend/build) from the API server."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse


def spa_router(build_dir: Path) -> APIRouter:
    """
    Static files from the SvelteKit build, with every other non-API path
    falling back to index.html so client-side routes (/analysis/<id>/...)
    work on reload and as shared links.
    """
    root = build_dir.resolve()
    router = APIRouter(include_in_schema=False)

    @router.get("/{path:path}")
    def serve(path: str) -> FileResponse:
        if path.startswith("api/") or path == "api":
            raise HTTPException(status_code=404, detail="Not found")
        if path:
            candidate = (root / path).resolve()
            if candidate.is_file() and root in candidate.parents:
                return FileResponse(candidate)
        return FileResponse(root / "index.html")

    return router
