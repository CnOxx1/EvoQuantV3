import csv
import io
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from functools import wraps

from loguru import logger

from config.settings import MACRO_CONFIG, MAX_RETRIES, RETRY_DELAY


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
                    f"[{func.__name__}] 宏观数据请求失败 "
                    f"(第{attempt}/{MAX_RETRIES}次): {exc}"
                )
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY * attempt)
        raise last_exception

    return wrapper


class MacroDataClient:
    """宏观数据 HTTP 客户端。"""

    YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"

    def __init__(self):
        self.timeout_seconds = MACRO_CONFIG["timeout_seconds"]
        self.user_agent = MACRO_CONFIG["user_agent"]

    @staticmethod
    def _to_epoch_seconds(value: datetime) -> int:
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        else:
            value = value.astimezone(timezone.utc)
        return int(value.timestamp())

    def _build_request(self, url: str) -> urllib.request.Request:
        return urllib.request.Request(
            url,
            headers={
                "User-Agent": self.user_agent,
                "Accept": "application/json,text/csv,text/plain;q=0.9,*/*;q=0.8",
            },
        )

    @retry_on_failure
    def _fetch_text(self, url: str) -> str:
        request = self._build_request(url)
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            return response.read().decode("utf-8")

    @retry_on_failure
    def _fetch_json(self, url: str) -> dict:
        return json.loads(self._fetch_text(url))

    def fetch_yahoo_chart(
        self,
        symbol: str,
        interval: str,
        start_at: datetime,
        end_at: datetime | None = None,
    ) -> dict:
        params = {
            "interval": interval,
            "includePrePost": "false",
            "events": "div,splits",
            "period1": str(self._to_epoch_seconds(start_at)),
            "period2": str(
                self._to_epoch_seconds(end_at or datetime.now(timezone.utc))
            ),
        }
        url = self.YAHOO_CHART_URL.format(symbol=urllib.parse.quote(symbol, safe=""))
        url = f"{url}?{urllib.parse.urlencode(params)}"
        return self._fetch_json(url)

    def fetch_fred_series(
        self,
        series_id: str,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> list[dict[str, str]]:
        params = {"id": series_id}
        if start_date is not None:
            params["cosd"] = start_date.date().isoformat()
        if end_date is not None:
            params["coed"] = end_date.date().isoformat()
        url = f"{self.FRED_CSV_URL}?{urllib.parse.urlencode(params)}"
        payload = self._fetch_text(url)
        reader = csv.DictReader(io.StringIO(payload))
        return [dict(row) for row in reader]
