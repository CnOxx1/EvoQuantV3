from __future__ import annotations

import json as _json
from typing import Iterator

try:
    import orjson
    def _dumps(obj: dict) -> str:
        return orjson.dumps(obj).decode()
except ImportError:
    def _dumps(obj: dict) -> str:
        return _json.dumps(obj, separators=(",", ":"))

from fastapi.responses import StreamingResponse


def stream_json_array(items_generator: Iterator[dict], chunk_size: int = 100) -> StreamingResponse:
    def _generate():
        first = True
        yield "["
        chunk: list[str] = []
        for item in items_generator:
            chunk.append(_dumps(item))
            if len(chunk) >= chunk_size:
                prefix = "" if first else ","
                yield prefix + ",".join(chunk)
                first = False
                chunk = []
        if chunk:
            prefix = "" if first else ","
            yield prefix + ",".join(chunk)
        yield "]"

    return StreamingResponse(_generate(), media_type="application/json")


def stream_ndjson(items_generator: Iterator[dict]) -> StreamingResponse:
    def _generate():
        for item in items_generator:
            yield _dumps(item) + "\n"

    return StreamingResponse(_generate(), media_type="application/x-ndjson")
