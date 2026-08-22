"""Run EvoQuant's formal logic pipeline and emit a concise JSON verification report."""

from __future__ import annotations

import json
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def main() -> int:
    from config.logging import setup_logger
    from logic_layer.logic_pipeline.service import run_full_pipeline

    setup_logger("pipeline_verification")
    started_at = datetime.now(timezone.utc).isoformat()
    try:
        result = run_full_pipeline()
    except Exception as exc:  # pragma: no cover - operational safety path
        print(
            json.dumps(
                {
                    "status": "error",
                    "started_at": started_at,
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "traceback": traceback.format_exc(),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1

    print(
        json.dumps(
            {
                "status": "completed",
                "started_at": started_at,
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "pipeline": result,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
