"""Run EvoQuant anomaly detection once using the project's live SQLite inputs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbols", default="", help="Optional comma-separated asset symbols")
    args = parser.parse_args()

    from config.logging import setup_logger
    from logic_layer.anomaly_detection.service import AnomalyDetectionService

    setup_logger("anomaly_detection")
    symbols = [item.strip() for item in args.symbols.split(",") if item.strip()] or None
    service = AnomalyDetectionService()
    try:
        service.init_storage()
        result = service.run_detection(symbols=symbols, save=True)
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    finally:
        service.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
