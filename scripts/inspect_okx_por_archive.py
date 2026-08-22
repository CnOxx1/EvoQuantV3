"""Inspect an OKX Proof-of-Reserves CSV archive without executing its contents."""

from __future__ import annotations

import argparse
import csv
import io
import json
import zipfile

import httpx


DEFAULT_URL = "https://static.okx.com/cdn/okx/por/chain/por_csv_2026070700_V3.zip"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=DEFAULT_URL)
    args = parser.parse_args()
    response = httpx.get(args.url, timeout=60, follow_redirects=True)
    response.raise_for_status()
    archive = zipfile.ZipFile(io.BytesIO(response.content))
    files = []
    for info in archive.infolist():
        item = {"name": info.filename, "size": info.file_size}
        if info.filename.lower().endswith(".csv"):
            with archive.open(info) as handle:
                reader = csv.reader(io.TextIOWrapper(handle, encoding="utf-8-sig", errors="replace"))
                item["header"] = next(reader, [])
                item["sample"] = next(reader, [])
        files.append(item)
    print(json.dumps({"url": args.url, "files": files}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
