import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from functools import wraps

from loguru import logger

from config.settings import ALTERNATIVE_CONFIG, MAX_RETRIES, RETRY_DELAY


class GitHubRateLimitExceededError(RuntimeError):
    """GitHub API 已触发 rate limit，当前不应继续重试。"""


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
                    f"[{func.__name__}] 补充特征请求失败 "
                    f"(第{attempt}/{MAX_RETRIES}次): {exc}"
                )
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY * attempt)
        raise last_exception

    return wrapper


class AlternativeDataClient:
    """补充特征 HTTP 客户端。"""

    GENERIC_CHAIN_HISTORY_KEYS = {
        "chart",
        "chains",
        "circulating",
        "circulation",
        "data",
        "distribution",
        "history",
        "mcap",
        "peggedassets",
        "peggedusd",
        "results",
        "rows",
        "series",
        "supply",
        "timeline",
        "totalcirculating",
        "totalcirculatingusd",
        "values",
    }

    def __init__(self):
        self.user_agent = ALTERNATIVE_CONFIG["user_agent"]
        self.github_timeout_seconds = ALTERNATIVE_CONFIG["github_timeout_seconds"]
        self.github_token = ALTERNATIVE_CONFIG["github_token"]
        self.github_rest_base_url = ALTERNATIVE_CONFIG["github_rest_base_url"]
        self.stablecoin_timeout_seconds = ALTERNATIVE_CONFIG["stablecoin_timeout_seconds"]
        self.stablecoin_rest_base_url = ALTERNATIVE_CONFIG["stablecoin_rest_base_url"]
        self.google_trends_timeout_seconds = ALTERNATIVE_CONFIG["google_trends_timeout_seconds"]
        self.google_trends_base_url = ALTERNATIVE_CONFIG["google_trends_base_url"]
        self.google_trends_hl = ALTERNATIVE_CONFIG["google_trends_hl"]
        self.google_trends_tz = ALTERNATIVE_CONFIG["google_trends_tz"]
        if ALTERNATIVE_CONFIG["enable_github"] and not self.github_token:
            logger.warning(
                "GitHub 补充特征已启用，但当前未配置 GITHUB_TOKEN；"
                "GitHub Search API 很容易触发 rate limit。"
                "建议设置 GITHUB_TOKEN，或临时关闭 ALTERNATIVE_ENABLE_GITHUB。"
            )

    @staticmethod
    def _to_iso8601(value: datetime) -> str:
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        else:
            value = value.astimezone(timezone.utc)
        return value.strftime("%Y-%m-%dT%H:%M:%SZ")

    def _build_request(
        self,
        url: str,
        accept: str = "application/json",
    ) -> urllib.request.Request:
        headers = {
            "User-Agent": self.user_agent,
            "Accept": accept,
        }
        if self.github_token and url.startswith(self.github_rest_base_url):
            headers["Authorization"] = f"Bearer {self.github_token}"
            headers["X-GitHub-Api-Version"] = "2022-11-28"
        if url.startswith(self.google_trends_base_url):
            headers["Referer"] = f"{self.google_trends_base_url}/explore"
            headers["Accept-Language"] = self.google_trends_hl
        return urllib.request.Request(url, headers=headers)

    @staticmethod
    def _format_rate_limit_reset(headers) -> str | None:
        if not headers:
            return None
        reset_at_raw = headers.get("X-RateLimit-Reset")
        if not reset_at_raw:
            return None
        try:
            reset_at = datetime.fromtimestamp(int(reset_at_raw), tz=timezone.utc)
        except (TypeError, ValueError, OSError):
            return None
        return reset_at.strftime("%Y-%m-%d %H:%M:%S UTC")

    def _raise_if_github_rate_limited(self, url: str, error: urllib.error.HTTPError):
        if not url.startswith(self.github_rest_base_url):
            return
        if error.code not in {403, 429}:
            return

        headers = getattr(error, "headers", None)
        remaining = (headers.get("X-RateLimit-Remaining") if headers else None) or ""
        error_text = str(error).lower()

        if remaining != "0" and "rate limit" not in error_text:
            return

        reset_at = self._format_rate_limit_reset(headers)
        message = "GitHub API rate limit exceeded"
        if reset_at:
            message += f"，预计重置时间: {reset_at}"
        if not self.github_token:
            message += "；当前未配置 GITHUB_TOKEN"
        raise GitHubRateLimitExceededError(message) from error

    @retry_on_failure
    def _fetch_text(self, url: str, timeout_seconds: int) -> str:
        request = self._build_request(url)
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                return response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            self._raise_if_github_rate_limited(url, exc)
            raise

    @retry_on_failure
    def _fetch_json(self, url: str, timeout_seconds: int) -> dict | list:
        return json.loads(self._fetch_text(url, timeout_seconds))

    def fetch_github_commits(
        self,
        owner: str,
        repo: str,
        since: datetime,
        until: datetime | None = None,
        per_page: int = 100,
        max_pages: int = 10,
    ) -> list[dict]:
        params = {
            "since": self._to_iso8601(since),
            "per_page": str(per_page),
        }
        if until is not None:
            params["until"] = self._to_iso8601(until)

        results: list[dict] = []
        for page in range(1, max_pages + 1):
            page_params = {**params, "page": str(page)}
            url = (
                f"{self.github_rest_base_url}/repos/"
                f"{urllib.parse.quote(owner, safe='')}/"
                f"{urllib.parse.quote(repo, safe='')}/commits?"
                f"{urllib.parse.urlencode(page_params)}"
            )
            payload = self._fetch_json(url, self.github_timeout_seconds)
            if not isinstance(payload, list):
                break
            results.extend(payload)
            if len(payload) < per_page:
                break
        return results

    def search_github_pull_request_count(
        self,
        owner: str,
        repo: str,
        qualifier: str,
        since: datetime,
    ) -> int:
        if qualifier not in {"created", "merged"}:
            raise ValueError(f"不支持的 GitHub PR qualifier: {qualifier}")

        query = (
            f"repo:{owner}/{repo} "
            f"is:pr {qualifier}:>={self._to_iso8601(since)}"
        )
        url = (
            f"{self.github_rest_base_url}/search/issues?"
            f"{urllib.parse.urlencode({'q': query, 'per_page': '1'})}"
        )
        payload = self._fetch_json(url, self.github_timeout_seconds)
        if not isinstance(payload, dict):
            return 0
        return int(payload.get("total_count") or 0)

    def fetch_github_releases(
        self,
        owner: str,
        repo: str,
        per_page: int = 100,
        max_pages: int = 5,
    ) -> list[dict]:
        results: list[dict] = []
        for page in range(1, max_pages + 1):
            url = (
                f"{self.github_rest_base_url}/repos/"
                f"{urllib.parse.quote(owner, safe='')}/"
                f"{urllib.parse.quote(repo, safe='')}/releases?"
                f"{urllib.parse.urlencode({'per_page': str(per_page), 'page': str(page)})}"
            )
            payload = self._fetch_json(url, self.github_timeout_seconds)
            if not isinstance(payload, list):
                break
            results.extend(payload)
            if len(payload) < per_page:
                break
        return results

    def fetch_stablecoin_assets(self) -> list[dict]:
        payload = self._fetch_json(
            f"{self.stablecoin_rest_base_url}/stablecoins?includePrices=true",
            self.stablecoin_timeout_seconds,
        )
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if not isinstance(payload, dict):
            return []
        rows = (
            payload.get("peggedAssets")
            or payload.get("assets")
            or payload.get("data")
            or []
        )
        return [item for item in rows if isinstance(item, dict)]

    def fetch_stablecoin_history(self, asset_id: str | int) -> list[dict]:
        payload = self._fetch_json(
            f"{self.stablecoin_rest_base_url}/stablecoin/{asset_id}",
            self.stablecoin_timeout_seconds,
        )
        return self._normalize_stablecoin_history(payload)

    def fetch_stablecoin_chain_history(self, asset_id: str | int) -> list[dict]:
        payload = self._fetch_json(
            f"{self.stablecoin_rest_base_url}/stablecoin/{asset_id}",
            self.stablecoin_timeout_seconds,
        )
        return self._normalize_stablecoin_chain_history(payload)

    def fetch_google_trends_interest(
        self,
        query: str,
        timeframe: str,
        geo: str = "",
        category: int = 0,
        gprop: str = "",
        hl: str | None = None,
        tz: int | None = None,
    ) -> list[dict]:
        explore_payload, common_params = self._fetch_google_trends_explore_payload(
            query=query,
            timeframe=timeframe,
            geo=geo,
            category=category,
            gprop=gprop,
            hl=hl,
            tz=tz,
        )
        widget = self._find_timeseries_widget(explore_payload)
        if widget is None:
            return []

        timeline_payload = self._fetch_google_trends_widget_payload(
            endpoint="widgetdata/multiline",
            widget=widget,
            common_params=common_params,
        )
        return self._normalize_google_trends_timeline(timeline_payload)

    def fetch_google_trends_related_queries(
        self,
        query: str,
        timeframe: str,
        geo: str = "",
        category: int = 0,
        gprop: str = "",
        hl: str | None = None,
        tz: int | None = None,
    ) -> dict[str, list[dict]]:
        explore_payload, common_params = self._fetch_google_trends_explore_payload(
            query=query,
            timeframe=timeframe,
            geo=geo,
            category=category,
            gprop=gprop,
            hl=hl,
            tz=tz,
        )
        widget = self._find_related_widget(
            explore_payload,
            widget_kind="queries",
        )
        if widget is None:
            return {
                "top": [],
                "rising": [],
            }
        related_payload = self._fetch_google_trends_widget_payload(
            endpoint="widgetdata/relatedsearches",
            widget=widget,
            common_params=common_params,
        )
        return self._normalize_google_trends_related_ranked_lists(
            related_payload,
            item_type="query",
        )

    def fetch_google_trends_related_topics(
        self,
        query: str,
        timeframe: str,
        geo: str = "",
        category: int = 0,
        gprop: str = "",
        hl: str | None = None,
        tz: int | None = None,
    ) -> dict[str, list[dict]]:
        explore_payload, common_params = self._fetch_google_trends_explore_payload(
            query=query,
            timeframe=timeframe,
            geo=geo,
            category=category,
            gprop=gprop,
            hl=hl,
            tz=tz,
        )
        widget = self._find_related_widget(
            explore_payload,
            widget_kind="topics",
        )
        if widget is None:
            return {
                "top": [],
                "rising": [],
            }
        related_payload = self._fetch_google_trends_widget_payload(
            endpoint="widgetdata/relatedsearches",
            widget=widget,
            common_params=common_params,
        )
        return self._normalize_google_trends_related_ranked_lists(
            related_payload,
            item_type="topic",
        )

    def _fetch_google_trends_explore_payload(
        self,
        query: str,
        timeframe: str,
        geo: str = "",
        category: int = 0,
        gprop: str = "",
        hl: str | None = None,
        tz: int | None = None,
    ) -> tuple[dict | list, dict[str, str]]:
        payload = {
            "comparisonItem": [
                {
                    "keyword": query,
                    "geo": geo,
                    "time": timeframe,
                }
            ],
            "category": category,
            "property": gprop,
        }
        common_params = {
            "hl": hl or self.google_trends_hl,
            "tz": str(self.google_trends_tz if tz is None else tz),
        }
        explore_url = (
            f"{self.google_trends_base_url}/api/explore?"
            f"{urllib.parse.urlencode({**common_params, 'req': json.dumps(payload, separators=(',', ':'))})}"
        )
        return (
            self._fetch_google_trends_json(
                explore_url,
                self.google_trends_timeout_seconds,
            ),
            common_params,
        )

    def _fetch_google_trends_widget_payload(
        self,
        endpoint: str,
        widget: dict,
        common_params: dict[str, str],
    ) -> dict | list:
        widget_request = widget.get("request") or {}
        widget_params = {
            **common_params,
            "token": widget.get("token", ""),
            "req": json.dumps(widget_request, separators=(",", ":")),
        }
        widget_url = (
            f"{self.google_trends_base_url}/api/{endpoint}?"
            f"{urllib.parse.urlencode(widget_params)}"
        )
        return self._fetch_google_trends_json(
            widget_url,
            self.google_trends_timeout_seconds,
        )

    def _fetch_google_trends_json(
        self,
        url: str,
        timeout_seconds: int,
    ) -> dict | list:
        return json.loads(self._strip_xssi_prefix(self._fetch_text(url, timeout_seconds)))

    @staticmethod
    def _strip_xssi_prefix(payload: str) -> str:
        start_indexes = [
            index
            for index in (
                payload.find("{"),
                payload.find("["),
            )
            if index >= 0
        ]
        if not start_indexes:
            return payload
        return payload[min(start_indexes):]

    @staticmethod
    def _find_timeseries_widget(payload: dict | list) -> dict | None:
        if not isinstance(payload, dict):
            return None
        widgets = payload.get("widgets") or []
        for widget in widgets:
            widget_id = str(widget.get("id") or "").upper()
            if "TIMESERIES" in widget_id:
                return widget
        for widget in widgets:
            title = str(widget.get("title") or "").lower()
            if "interest over time" in title:
                return widget
        return None

    @staticmethod
    def _find_related_widget(
        payload: dict | list,
        widget_kind: str,
    ) -> dict | None:
        if widget_kind not in {"queries", "topics"}:
            raise ValueError(f"不支持的 Google Trends related widget 类型: {widget_kind}")
        if not isinstance(payload, dict):
            return None
        id_keyword = "RELATED_QUERIES" if widget_kind == "queries" else "RELATED_TOPICS"
        title_keyword = "related queries" if widget_kind == "queries" else "related topics"
        widgets = payload.get("widgets") or []
        for widget in widgets:
            widget_id = str(widget.get("id") or "").upper()
            if id_keyword in widget_id:
                return widget
        for widget in widgets:
            title = str(widget.get("title") or "").lower()
            if title_keyword in title:
                return widget
        return None

    @classmethod
    def _normalize_google_trends_timeline(cls, payload: dict | list) -> list[dict]:
        if not isinstance(payload, dict):
            return []
        timeline_data = ((payload.get("default") or {}).get("timelineData") or [])
        normalized: list[dict] = []
        for row in timeline_data:
            timestamp = cls._parse_timestamp(row.get("time"))
            values = row.get("value") or []
            if timestamp is None or not values:
                continue
            value = cls._extract_number(values[0])
            if value is None:
                continue
            has_data = row.get("hasData")
            if isinstance(has_data, list):
                has_data = bool(has_data[0]) if has_data else True
            elif has_data is None:
                has_data = True
            normalized.append(
                {
                    "timestamp": timestamp,
                    "value": float(value),
                    "formatted_time": row.get("formattedTime"),
                    "has_data": bool(has_data),
                    "is_partial": bool(row.get("isPartial")),
                }
            )
        normalized.sort(key=lambda item: item["timestamp"])
        return normalized

    @classmethod
    def _normalize_google_trends_related_ranked_lists(
        cls,
        payload: dict | list,
        item_type: str,
    ) -> dict[str, list[dict]]:
        if item_type not in {"query", "topic"}:
            raise ValueError(f"不支持的 Google Trends related item 类型: {item_type}")
        results = {
            "top": [],
            "rising": [],
        }
        if not isinstance(payload, dict):
            return results

        ranked_lists = ((payload.get("default") or {}).get("rankedList") or [])
        for index, ranked_list in enumerate(ranked_lists):
            ranking_type = cls._infer_google_trends_related_list_type(
                ranked_list,
                index=index,
            )
            entries: list[dict] = []
            for item in ranked_list.get("rankedKeyword") or []:
                if not isinstance(item, dict):
                    continue
                title = (
                    item.get("query")
                    or item.get("topic_title")
                    or item.get("title")
                )
                if not title:
                    continue
                formatted_value = str(item.get("formattedValue") or "").strip()
                is_breakout = formatted_value.lower() == "breakout"
                value = cls._extract_number(item.get("value"))
                if value is None and is_breakout:
                    value = 5000.0
                entries.append(
                    {
                        "type": item_type,
                        "title": str(title),
                        "value": float(value or 0.0),
                        "formatted_value": formatted_value,
                        "is_breakout": is_breakout,
                        "topic_mid": item.get("topic_mid"),
                        "topic_type": item.get("topic_type"),
                        "link": item.get("link"),
                    }
                )
            results[ranking_type] = entries
        return results

    @staticmethod
    def _infer_google_trends_related_list_type(
        ranked_list: dict,
        index: int,
    ) -> str:
        hints = " ".join(
            str(ranked_list.get(key) or "")
            for key in (
                "name",
                "title",
                "rankedListTitle",
            )
        ).lower()
        if "rising" in hints:
            return "rising"
        if "top" in hints:
            return "top"
        return "rising" if index == 1 else "top"

    @classmethod
    def _normalize_stablecoin_history(cls, payload: dict | list) -> list[dict]:
        if isinstance(payload, list):
            return cls._normalize_history_rows(payload)

        if not isinstance(payload, dict):
            return []

        direct_rows = payload.get("history")
        if isinstance(direct_rows, list):
            return cls._normalize_history_rows(direct_rows)

        candidate_lists: list[list[dict]] = []

        def visit(value):
            if isinstance(value, list):
                dict_items = [item for item in value if isinstance(item, dict)]
                if dict_items:
                    candidate_lists.append(dict_items)
                for item in value:
                    visit(item)
            elif isinstance(value, dict):
                for nested in value.values():
                    visit(nested)

        visit(payload)
        for rows in sorted(candidate_lists, key=len, reverse=True):
            normalized = cls._normalize_history_rows(rows)
            if normalized:
                return normalized
        return []

    @classmethod
    def _normalize_stablecoin_chain_history(
        cls,
        payload: dict | list,
    ) -> list[dict]:
        if isinstance(payload, list):
            return cls._normalize_chain_history_snapshots(payload)
        if not isinstance(payload, dict):
            return []

        candidate_snapshots: list[list[dict]] = []

        def visit(value):
            if isinstance(value, list):
                dict_items = [item for item in value if isinstance(item, dict)]
                if dict_items:
                    candidate_snapshots.append(dict_items)
                for item in value:
                    visit(item)
            elif isinstance(value, dict):
                for nested in value.values():
                    visit(nested)

        visit(payload)

        best_snapshots: list[dict] = []
        best_chain_point_count = 0
        for snapshot_rows in candidate_snapshots:
            normalized_snapshots = cls._normalize_chain_history_snapshots(snapshot_rows)
            chain_point_count = sum(
                len(snapshot.get("chains") or [])
                for snapshot in normalized_snapshots
            )
            if chain_point_count > best_chain_point_count:
                best_snapshots = normalized_snapshots
                best_chain_point_count = chain_point_count

        per_chain_snapshots = cls._normalize_chain_history_per_chain_series(payload)
        per_chain_point_count = sum(
            len(snapshot.get("chains") or [])
            for snapshot in per_chain_snapshots
        )
        if per_chain_point_count > best_chain_point_count:
            return per_chain_snapshots
        return best_snapshots

    @classmethod
    def _normalize_chain_history_snapshots(
        cls,
        rows: list[dict],
    ) -> list[dict]:
        snapshots: list[dict] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            timestamp = cls._parse_timestamp(
                row.get("timestamp")
                or row.get("date")
                or row.get("time")
                or row.get("datetime")
            )
            if timestamp is None:
                continue
            chains = cls._extract_chain_snapshot_rows(row)
            if not chains:
                continue
            snapshots.append(
                {
                    "timestamp": timestamp,
                    "chains": chains,
                }
            )
        snapshots.sort(key=lambda item: item["timestamp"])
        return snapshots

    @classmethod
    def _normalize_chain_history_per_chain_series(
        cls,
        payload: dict,
    ) -> list[dict]:
        rows_by_timestamp: dict[datetime, dict[str, float]] = {}

        def visit(value):
            if isinstance(value, dict):
                for chain_name, series in value.items():
                    chain_name_text = str(chain_name)
                    if cls._is_generic_chain_history_key(chain_name_text):
                        visit(series)
                        continue
                    if not isinstance(series, list):
                        visit(series)
                        continue
                    normalized_points: list[tuple[datetime, float]] = []
                    for item in series:
                        if not isinstance(item, dict):
                            continue
                        timestamp = cls._parse_timestamp(
                            item.get("timestamp")
                            or item.get("date")
                            or item.get("time")
                            or item.get("datetime")
                        )
                        supply = cls._extract_number(
                            item.get("supply")
                            or item.get("circulating")
                            or item.get("value")
                        )
                        if timestamp is None or supply is None:
                            continue
                        normalized_points.append((timestamp, float(supply)))
                    if normalized_points:
                        for timestamp, supply in normalized_points:
                            rows_by_timestamp.setdefault(timestamp, {})[str(chain_name)] = supply
                        continue
                    for nested in series:
                        visit(nested)
            elif isinstance(value, list):
                for item in value:
                    visit(item)

        visit(payload)

        snapshots = [
            {
                "timestamp": timestamp,
                "chains": [
                    {
                        "chain": chain_name,
                        "supply": supply,
                    }
                    for chain_name, supply in sorted(chains.items())
                    if supply > 0
                ],
            }
            for timestamp, chains in sorted(rows_by_timestamp.items())
        ]
        return [snapshot for snapshot in snapshots if snapshot["chains"]]

    @classmethod
    def _is_generic_chain_history_key(cls, value: str) -> bool:
        normalized = (
            value.strip()
            .lower()
            .replace(" ", "")
            .replace("-", "")
            .replace("_", "")
        )
        return normalized in cls.GENERIC_CHAIN_HISTORY_KEYS

    @classmethod
    def _extract_chain_snapshot_rows(
        cls,
        row: dict,
    ) -> list[dict]:
        chain_fields = [
            row.get("chainCirculating"),
            row.get("chainBalances"),
            row.get("chain_distribution"),
            row.get("chains"),
            row.get("distribution"),
        ]
        for field in chain_fields:
            normalized = cls._normalize_chain_distribution_value(field, row=row)
            if normalized:
                return normalized
        return []

    @classmethod
    def _normalize_chain_distribution_value(
        cls,
        value,
        row: dict | None = None,
    ) -> list[dict]:
        normalized: list[dict] = []
        if isinstance(value, dict):
            for chain_name, chain_value in value.items():
                supply = cls._extract_number(chain_value)
                if supply is None or supply <= 0:
                    continue
                normalized.append(
                    {
                        "chain": str(chain_name),
                        "supply": float(supply),
                    }
                )
            return normalized

        if isinstance(value, list):
            for item in value:
                if not isinstance(item, dict):
                    continue
                chain_name = (
                    item.get("chain")
                    or item.get("name")
                    or item.get("chainName")
                    or item.get("title")
                )
                supply = cls._extract_number(
                    item.get("circulating")
                    or item.get("supply")
                    or item.get("value")
                )
                if not chain_name or supply is None or supply <= 0:
                    continue
                normalized.append(
                    {
                        "chain": str(chain_name),
                        "supply": float(supply),
                    }
                )
            if normalized:
                return normalized

        if row is not None and isinstance(value, list):
            chain_names = [
                item
                for item in value
                if isinstance(item, str)
            ]
            chain_balances = row.get("chainBalances") or row.get("chain_distribution")
            if chain_names and isinstance(chain_balances, list):
                for chain_name, chain_value in zip(chain_names, chain_balances):
                    supply = cls._extract_number(chain_value)
                    if supply is None or supply <= 0:
                        continue
                    normalized.append(
                        {
                            "chain": str(chain_name),
                            "supply": float(supply),
                        }
                    )
        return normalized

    @classmethod
    def _normalize_history_rows(cls, rows: list[dict]) -> list[dict]:
        normalized: list[dict] = []
        for row in rows:
            timestamp = cls._parse_timestamp(
                row.get("timestamp")
                or row.get("date")
                or row.get("time")
                or row.get("datetime")
            )
            supply = cls._extract_number(
                row.get("supply")
                or row.get("circulating")
                or row.get("totalCirculating")
                or row.get("totalCirculatingUSD")
                or row.get("peggedUSD")
                or row.get("value")
            )
            if timestamp is None or supply is None:
                continue
            normalized.append(
                {
                    "timestamp": timestamp,
                    "supply": float(supply),
                }
            )
        normalized.sort(key=lambda item: item["timestamp"])
        return normalized

    @staticmethod
    def _parse_timestamp(value) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            if value.tzinfo is not None:
                return value.astimezone(timezone.utc).replace(tzinfo=None)
            return value
        if isinstance(value, (int, float)):
            if value > 10_000_000_000:
                value = value / 1000
            return datetime.fromtimestamp(value, tz=timezone.utc).replace(tzinfo=None)
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return None
            if value.isdigit():
                return AlternativeDataClient._parse_timestamp(int(value))
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                try:
                    parsed = datetime.fromisoformat(f"{value}T00:00:00")
                except ValueError:
                    return None
            if parsed.tzinfo is not None:
                return parsed.astimezone(timezone.utc).replace(tzinfo=None)
            return parsed
        return None

    @classmethod
    def _extract_number(cls, value) -> float | None:
        if value is None:
            return None
        if isinstance(value, bool):
            return float(int(value))
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            text = value.strip().replace(",", "")
            if not text:
                return None
            try:
                return float(text)
            except ValueError:
                return None
        if isinstance(value, dict):
            for key in (
                "peggedUSD",
                "circulating",
                "current",
                "value",
                "amount",
                "supply",
            ):
                nested = cls._extract_number(value.get(key))
                if nested is not None:
                    return nested
            for nested_value in value.values():
                nested = cls._extract_number(nested_value)
                if nested is not None:
                    return nested
        if isinstance(value, list):
            for item in value:
                nested = cls._extract_number(item)
                if nested is not None:
                    return nested
        return None
