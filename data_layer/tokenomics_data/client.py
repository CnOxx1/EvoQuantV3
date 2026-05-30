import json
import time
import urllib.error
import urllib.parse
import urllib.request
from functools import wraps

from loguru import logger

from config.settings import MAX_RETRIES, RETRY_DELAY, TOKENOMICS_CONFIG
from data_layer.tokenomics_data.models import TokenomicsSourceDefinition


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
                urllib.error.HTTPError,
                urllib.error.URLError,
                ValueError,
            ) as exc:
                last_exception = exc
                logger.warning(
                    f"[{func.__name__}] tokenomics 请求失败 "
                    f"(第{attempt}/{MAX_RETRIES}次): {exc}"
                )
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY * attempt)
        raise last_exception

    return wrapper


class TokenomicsDataClient:
    """Tokenomics 数据 HTTP 客户端。"""

    def __init__(self):
        self.timeout_seconds = TOKENOMICS_CONFIG["timeout_seconds"]
        self.user_agent = TOKENOMICS_CONFIG["user_agent"]

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
    def _extract_items(payload, key_candidates: tuple[str, ...]) -> list[dict]:
        if isinstance(payload, list):
            return [dict(item) for item in payload if isinstance(item, dict)]
        if not isinstance(payload, dict):
            raise ValueError("tokenomics payload 必须是 list 或 dict")
        for key in key_candidates:
            value = payload.get(key)
            if isinstance(value, list):
                return [dict(item) for item in value if isinstance(item, dict)]
        return []

    def _fetch_payload(
        self,
        source: TokenomicsSourceDefinition,
        entity_keys: list[str] | None = None,
        interval: str | None = None,
        lookback_hours: int | None = None,
    ):
        if not source.endpoint:
            logger.debug(f"tokenomics 来源 {source.source_name} 未配置 endpoint，跳过采集")
            return {}
        params = dict(source.params)
        if interval:
            params.setdefault("interval", interval)
        if lookback_hours is not None:
            params.setdefault("lookback_hours", lookback_hours)
        if entity_keys:
            params.setdefault("entities", ",".join(entity_keys))
        url = self._append_query(source.endpoint, params)
        return self._fetch_json(url)

    def fetch_points(
        self,
        source: TokenomicsSourceDefinition,
        entity_keys: list[str] | None = None,
        interval: str | None = None,
        lookback_hours: int | None = None,
    ) -> list[dict]:
        payload = self._fetch_payload(
            source=source,
            entity_keys=entity_keys,
            interval=interval,
            lookback_hours=lookback_hours,
        )
        return self._extract_items(payload, ("points", "items", "results", "data"))

    def fetch_events(
        self,
        source: TokenomicsSourceDefinition,
        entity_keys: list[str] | None = None,
        interval: str | None = None,
        lookback_hours: int | None = None,
    ) -> list[dict]:
        payload = self._fetch_payload(
            source=source,
            entity_keys=entity_keys,
            interval=interval,
            lookback_hours=lookback_hours,
        )
        return self._extract_items(payload, ("events", "items"))
