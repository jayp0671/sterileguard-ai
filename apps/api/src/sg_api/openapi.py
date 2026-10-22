"""Print the OpenAPI spec deterministically: `uv run python -m sg_api.openapi`."""

from __future__ import annotations

import json
import sys

from sg_api.core.config import Settings
from sg_api.main import create_app


def spec() -> str:
    app = create_app(Settings(env="test"))
    return json.dumps(app.openapi(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", newline="\n")  # type: ignore[union-attr]
    sys.stdout.write(spec())
