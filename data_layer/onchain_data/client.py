import json
import time
import urllib.error
import urllib.parse
import urllib.request
from functools import wraps

from loguru import logger

from config.settings import MAX_RETRIES, ONCHAIN_CONFIG, RETRY_DELAY
from data_layer.onchain_data.models import OnchainSourceDefinition


def retry_on_failure(func):
    """对 HTTP 采集调用做有限重试。"""

    @wraps(func)
    def wrapper(*args, **kwargs):
        last_exception = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                return func(*args, **kwargs)
            except (
                TimeoutError,
                OSError,
                urllib.error.HTTPError,
                urllib.error.URLError,
                ValueError,
            ) as exc:
                last_exception = exc
                logger.warning(
                    f"[{func.__name__}] 链上数据请求失败 "
                    f"(第{attempt}/{MAX_RETRIES}次): {exc}"
                )
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY * attempt)
        raise last_exception

    return wrapper


class OnchainDataClient:
    """链上数据 HTTP 客户端。"""

    def __init__(self):
        self.timeout_seconds = ONCHAIN_CONFIG["timeout_seconds"]
        # 使用浏览器 UA 避免 DeFiLlama 等 API 的 bot 检测 (402)
        self.user_agent = (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        )

    def _build_request(self, url: str) -> urllib.request.Request:
        return urllib.request.Request(
            url,
            headers={
                "User-Agent": self.user_agent,
                "Accept": "application/json,text/plain;q=0.9,*/*;q=0.8",
            },
        )

    @retry_on_failure
    def _fetch_text(self, url: str) -> str:
        request = self._build_request(url)
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            return response.read().decode("utf-8")

    @retry_on_failure
    def _fetch_json(self, url: str):
        return json.loads(self._fetch_text(url))

    @staticmethod
    def _append_query(url: str, params: dict[str, object]) -> str:
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

    @staticmethod
    def _extract_items(payload) -> list[dict]:
        if isinstance(payload, list):
            return [dict(item) for item in payload if isinstance(item, dict)]
        if not isinstance(payload, dict):
            raise ValueError("链上数据返回 payload 必须是 list 或 dict")

        for key in ("points", "items", "results", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                return [dict(item) for item in value if isinstance(item, dict)]
            if isinstance(value, dict):
                nested = value.get("points") or value.get("items")
                if isinstance(nested, list):
                    return [dict(item) for item in nested if isinstance(item, dict)]
        return []

    def fetch_points(
        self,
        source: OnchainSourceDefinition,
        entity_keys: list[str] | None = None,
        interval: str | None = None,
        lookback_hours: int | None = None,
    ) -> list[dict]:
        if not source.endpoint:
            logger.debug(f"链上来源 {source.source_name} 未配置 endpoint，跳过采集")
            return []

        params = dict(source.params)
        if interval:
            params.setdefault("interval", interval)
        if lookback_hours is not None:
            params.setdefault("lookback_hours", lookback_hours)
        if entity_keys:
            params.setdefault("entities", ",".join(entity_keys))
        url = self._append_query(source.endpoint, params)
        payload = self._fetch_json(url)
        return self._extract_items(payload)
