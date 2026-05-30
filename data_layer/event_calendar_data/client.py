import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from functools import wraps

from loguru import logger

from config.settings import EVENT_CALENDAR_CONFIG, MAX_RETRIES, RETRY_DELAY
from data_layer.event_calendar_data.models import EventCalendarSource


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
                    f"[{func.__name__}] 事件日历请求失败 "
                    f"(第{attempt}/{MAX_RETRIES}次): {exc}"
                )
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY * attempt)
        raise last_exception

    return wrapper


class EventCalendarClient:
    """事件日历 HTTP 客户端。"""

    def __init__(self):
        self.timeout_seconds = EVENT_CALENDAR_CONFIG["timeout_seconds"]
        self.user_agent = EVENT_CALENDAR_CONFIG["user_agent"]

    def _build_request(self, url: str) -> urllib.request.Request:
        return urllib.request.Request(
            url,
            headers={
                "User-Agent": self.user_agent,
                "Accept": "application/json,text/calendar,text/plain;q=0.9,*/*;q=0.8",
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
            raise ValueError("事件日历返回 payload 必须是 list 或 dict")

        for key in ("events", "items", "results", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                return [dict(item) for item in value if isinstance(item, dict)]
            if isinstance(value, dict):
                nested = value.get("events") or value.get("items")
                if isinstance(nested, list):
                    return [dict(item) for item in nested if isinstance(item, dict)]
        return []

    @staticmethod
    def _unfold_ics_lines(body: str) -> list[str]:
        lines = body.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        unfolded: list[str] = []
        for line in lines:
            if line.startswith((" ", "\t")) and unfolded:
                unfolded[-1] = f"{unfolded[-1]}{line[1:]}"
            else:
                unfolded.append(line)
        return unfolded

    @staticmethod
    def _parse_ics_datetime(value: str) -> datetime:
        text = value.strip()
        if text.endswith("Z"):
            return datetime.strptime(text, "%Y%m%dT%H%M%SZ").replace(
                tzinfo=timezone.utc
            )
        if "T" in text:
            return datetime.strptime(text, "%Y%m%dT%H%M%S").replace(
                tzinfo=timezone.utc
            )
        return datetime.strptime(text, "%Y%m%d").replace(tzinfo=timezone.utc)

    def _parse_ics(self, body: str, source: EventCalendarSource) -> list[dict]:
        events: list[dict] = []
        current: dict[str, str] | None = None
        for line in self._unfold_ics_lines(body):
            stripped = line.strip()
            if stripped == "BEGIN:VEVENT":
                current = {}
                continue
            if stripped == "END:VEVENT":
                if current and "DTSTART" in current and "SUMMARY" in current:
                    events.append(
                        {
                            "external_id": current.get("UID"),
                            "title": current.get("SUMMARY"),
                            "description": current.get("DESCRIPTION"),
                            "scheduled_at": self._parse_ics_datetime(current["DTSTART"]).isoformat(),
                            "status": (current.get("STATUS") or "scheduled").lower(),
                            "source_url": current.get("URL"),
                            "event_type": source.event_type,
                            "symbol": source.default_symbol,
                            "timezone": source.timezone,
                        }
                    )
                current = None
                continue
            if current is None or ":" not in line:
                continue
            raw_key, raw_value = line.split(":", 1)
            key = raw_key.split(";", 1)[0].upper()
            current[key] = raw_value.strip()
        return events

    def fetch_events(
        self,
        source: EventCalendarSource,
        lookahead_days: int | None = None,
    ) -> list[dict]:
        if not source.endpoint:
            logger.debug(f"事件源 {source.name} 未配置 endpoint，跳过采集")
            return []

        params = dict(source.params)
        if lookahead_days is not None:
            params.setdefault("lookahead_days", lookahead_days)
        url = self._append_query(source.endpoint, params)

        if source.adapter == "normalized_json":
            payload = self._fetch_json(url)
            return self._extract_items(payload)
        if source.adapter == "ics":
            body = self._fetch_text(url)
            return self._parse_ics(body, source)
        raise ValueError(f"未知事件源 adapter: {source.adapter}")
