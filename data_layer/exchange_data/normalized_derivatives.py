import json
import time
import urllib.parse
from functools import wraps

import httpx
from loguru import logger

from config.settings import EXCHANGE_DERIVATIVES_CONFIG, MAX_RETRIES, RETRY_DELAY


def retry_on_failure(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        last_exception = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                return func(*args, **kwargs)
            except (
                TimeoutError,
                OSError,
                httpx.HTTPStatusError,
                httpx.RequestError,
                ValueError,
            ) as exc:
                last_exception = exc
                logger.warning(
                    f"[{func.__name__}] 衍生品标准化请求失败 "
                    f"(第{attempt}/{MAX_RETRIES}次): {exc}"
                )
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY * attempt)
        raise last_exception

    return wrapper


class NormalizedDerivativesClient:
    """读取自定义标准化衍生品接口。"""

    def __init__(self):
        self.timeout_seconds = 20
        self.user_agent = EXCHANGE_DERIVATIVES_CONFIG["user_agent"]
        self._client = httpx.Client(
            timeout=self.timeout_seconds,
            headers={
                "User-Agent": self.user_agent,
                "Accept": "application/json,text/plain;q=0.9,*/*;q=0.8",
            },
            follow_redirects=True,
        )

    @retry_on_failure
    def _fetch_text(self, url: str) -> str:
        response = self._client.get(url)
        response.raise_for_status()
        return response.text

    @retry_on_failure
    def fetch_json(self, url: str):
        response = self._client.get(url)
        response.raise_for_status()
        return response.json()

    @staticmethod
    def append_query(url: str, params: dict[str, object]) -> str:
        if not params:
            return url
        parsed = urllib.parse.urlsplit(url)
        query_pairs = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
        for key, value in params.items():
            if value is None or value == "":
                continue
            query_pairs.append((key, str(value)))
        query = urllib.parse.urlencode(query_pairs)
        return urllib.parse.urlunsplit(
            (parsed.scheme, parsed.netloc, parsed.path, query, parsed.fragment)
        )

    def fetch_items(self, url: str, params: dict[str, object] | None = None) -> list[dict]:
        if not url:
            return []
        payload = self.fetch_json(self.append_query(url, params or {}))
        if isinstance(payload, list):
            return [dict(item) for item in payload if isinstance(item, dict)]
        if not isinstance(payload, dict):
            raise ValueError("标准化衍生品 payload 必须是 list 或 dict")
        for key in ("items", "points", "rows", "data", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return [dict(item) for item in value if isinstance(item, dict)]
        return []
