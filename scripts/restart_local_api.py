"""Restart the local EvoQuant API process and wait for its health endpoint."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]


def health(url: str) -> dict | None:
    try:
        with urlopen(url, timeout=3) as response:
            return json.load(response)
    except (URLError, OSError, ValueError):
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--pid", type=int, required=True, help="Existing API process ID to replace")
    parser.add_argument("--timeout", type=int, default=40)
    args = parser.parse_args()

    logs = ROOT / "reports"
    logs.mkdir(exist_ok=True)
    log_path = logs / "local_api_restart.log"
    # /health redirects to a legacy WMI endpoint that may legitimately report
    # degraded while optional legacy tables are absent. The data-domain status
    # route is the authoritative readiness contract for this local service.
    health_url = f"http://127.0.0.1:{args.port}/status/"

    # Terminate only the explicitly supplied listener process, never a broad
    # interpreter pattern. This does not alter any SQLite database files.
    stopped = subprocess.run(
        ["taskkill", "/PID", str(args.pid), "/T", "/F"],
        capture_output=True,
        text=True,
        check=False,
    )
    if stopped.returncode != 0:
        print(json.dumps({"status": "error", "stage": "stop", "detail": stopped.stderr or stopped.stdout}, ensure_ascii=False))
        return 1

    creationflags = 0
    if os.name == "nt":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS

    with log_path.open("a", encoding="utf-8") as log_file:
        process = subprocess.Popen(
            [sys.executable, "-m", "api.app", "--port", str(args.port)],
            cwd=ROOT,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            creationflags=creationflags,
        )

    deadline = time.monotonic() + args.timeout
    while time.monotonic() < deadline:
        payload = health(health_url)
        if payload is not None:
            print(
                json.dumps(
                    {
                        "status": "healthy",
                        "old_pid": args.pid,
                        "new_pid": process.pid,
                        "health_url": health_url,
                        "health": payload,
                        "log": str(log_path),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0
        time.sleep(1)

    print(
        json.dumps(
            {
                "status": "timeout",
                "old_pid": args.pid,
                "new_pid": process.pid,
                "health_url": health_url,
                "log": str(log_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
