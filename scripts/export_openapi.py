"""Write the FastAPI OpenAPI schema to frontend/openapi.json (input for the typed client)."""

import json
from pathlib import Path

from backend.api.main import app

out = Path(__file__).resolve().parent.parent / "frontend" / "openapi.json"
out.write_text(json.dumps(app.openapi(), indent=2) + "\n", encoding="utf-8")
print(f"wrote {out}")
