"""Export the FastAPI OpenAPI schema for TypeScript client generation (make api-client)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from apps.api.main import app  # noqa: E402

out = Path(__file__).resolve().parents[1] / "apps" / "web" / "openapi.json"
out.write_text(json.dumps(app.openapi(), indent=1), encoding="utf-8")
print(f"wrote {out}")
