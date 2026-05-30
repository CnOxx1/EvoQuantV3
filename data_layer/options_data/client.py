import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from functools import wraps

from loguru import logger

from config.settings import MAX_RETRIES, OPTIONS_CONFIG, RETRY_DELAY
from data_layer.options_data.models import OptionsSourceDefinition


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
                    f"[{func.__name__}] options 请求失败 "
                    f"(第{attempt}/{MAX_RETRIES}次): {exc}"
                )
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY * attempt)
        raise last_exception

    return wrapper


class OptionsDataClient:
    """期权数据 HTTP 客户端。

    当配置的 endpoint 为空时，自动使用 Deribit 公开 API 作为数据源。
    """

    def __init__(self):
        self.timeout_seconds = OPTIONS_CONFIG["timeout_seconds"]
        self.user_agent = OPTIONS_CONFIG["user_agent"]
        self._deribit = None

    @property
    def deribit(self):
        if self._deribit is None:
            from data_layer.options_data.deribit_client import DeribitClient
            self._deribit = DeribitClient()
        return self._deribit

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
            raise ValueError("options payload 必须是 list 或 dict")
        for key in key_candidates:
            value = payload.get(key)
            if isinstance(value, list):
                return [dict(item) for item in value if isinstance(item, dict)]
        return []

    def _fetch_payload(
        self,
        source: OptionsSourceDefinition,
        entity_keys: list[str] | None = None,
        interval: str | None = None,
        lookback_hours: int | None = None,
    ):
        if not source.endpoint:
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

    def fetch_surface_snapshots(
        self,
        source: OptionsSourceDefinition,
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
        rows = self._extract_items(
            payload,
            ("surface_snapshots", "snapshots", "items", "results", "data"),
        )
        if rows:
            return rows
        return self._deribit_surface_snapshots(entity_keys, interval)

    def fetch_positioning_snapshots(
        self,
        source: OptionsSourceDefinition,
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
        rows = self._extract_items(
            payload,
            ("positioning_snapshots", "snapshots", "items", "results", "data"),
        )
        if rows:
            return rows
        return self._deribit_positioning_snapshots(entity_keys, interval)

    def fetch_relative_value_snapshots(
        self,
        source: OptionsSourceDefinition,
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
        rows = self._extract_items(
            payload,
            ("relative_value_snapshots", "snapshots", "items", "results", "data"),
        )
        if rows:
            return rows
        return self._deribit_relative_value_snapshots(entity_keys, interval)

    def fetch_strike_concentration_snapshots(
        self,
        source: OptionsSourceDefinition,
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
        rows = self._extract_items(
            payload,
            ("strike_concentration_snapshots", "snapshots", "items", "results", "data"),
        )
        if rows:
            return rows
        return self._deribit_strike_concentration_snapshots(entity_keys, interval)

    def fetch_gamma_exposure_snapshots(
        self,
        source: OptionsSourceDefinition,
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
        rows = self._extract_items(
            payload,
            ("gamma_exposure_snapshots", "snapshots", "items", "results", "data"),
        )
        if rows:
            return rows
        return self._deribit_gamma_exposure_snapshots(entity_keys, interval)

    def fetch_flow_activity_snapshots(
        self,
        source: OptionsSourceDefinition,
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
        rows = self._extract_items(
            payload,
            ("flow_activity_snapshots", "snapshots", "items", "results", "data"),
        )
        if rows:
            return rows
        return self._deribit_flow_activity_snapshots(entity_keys, interval)

    def fetch_expiry_structure_snapshots(
        self,
        source: OptionsSourceDefinition,
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
        rows = self._extract_items(
            payload,
            ("expiry_structure_snapshots", "snapshots", "items", "results", "data"),
        )
        if rows:
            return rows
        return self._deribit_expiry_structure_snapshots(entity_keys, interval)

    def fetch_hedge_pressure_snapshots(
        self,
        source: OptionsSourceDefinition,
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
        rows = self._extract_items(
            payload,
            ("hedge_pressure_snapshots", "snapshots", "items", "results", "data"),
        )
        if rows:
            return rows
        return self._deribit_hedge_pressure_snapshots(entity_keys, interval)

    # ─── Deribit fallback implementations ───────────────────────────────

    def _deribit_target_currencies(
        self, entity_keys: list[str] | None
    ) -> list[str]:
        currencies = self.deribit.SUPPORTED_CURRENCIES
        if entity_keys:
            upper = [k.upper() for k in entity_keys]
            currencies = [c for c in currencies if c in upper]
        return currencies

    def _deribit_surface_snapshots(
        self, entity_keys: list[str] | None, interval: str | None
    ) -> list[dict]:
        now_iso = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
        rows: list[dict] = []
        for currency in self._deribit_target_currencies(entity_keys):
            try:
                summaries = self.deribit.get_book_summary_by_currency(currency)
                hist_vol = self.deribit.get_historical_volatility(currency)
            except Exception as exc:
                logger.warning(f"Deribit surface fallback 失败 [{currency}]: {exc}")
                continue
            # 计算 ATM IV: 取 mark_iv 中位数作为近似
            ivs = [s["mark_iv"] for s in summaries if s.get("mark_iv") and s["mark_iv"] > 0]
            atm_iv_30d = sorted(ivs)[len(ivs) // 2] / 100 if ivs else None
            # 短期 IV: 取到期 < 8天的期权 IV 中位数
            short_ivs = []
            for s in summaries:
                name = s.get("instrument_name", "")
                iv = s.get("mark_iv", 0)
                if iv > 0 and self._is_near_expiry(name, days=8):
                    short_ivs.append(iv)
            atm_iv_7d = sorted(short_ivs)[len(short_ivs) // 2] / 100 if short_ivs else None
            rows.append({
                "entity_key": currency,
                "observation_time": now_iso,
                "interval": interval or "1h",
                "atm_iv_7d": atm_iv_7d,
                "atm_iv_30d": atm_iv_30d,
                "quality_flag": "ok",
                "source_symbol": f"{currency}-DERIBIT-IV",
                "raw_payload_json": json.dumps({
                    "source": "deribit", "iv_count": len(ivs),
                }),
            })
        return rows

    @staticmethod
    def _is_near_expiry(instrument_name: str, days: int = 8) -> bool:
        """判断期权合约是否在 N 天内到期。"""
        import re
        from datetime import timedelta
        match = re.search(r"-(\d{1,2})([A-Z]{3})(\d{2})-", instrument_name)
        if not match:
            return False
        day, mon_str, year_short = match.groups()
        months = {
            "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
            "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
        }
        mon = months.get(mon_str, 0)
        if not mon:
            return False
        try:
            expiry = datetime(2000 + int(year_short), mon, int(day))
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            return (expiry - now) < timedelta(days=days)
        except (ValueError, TypeError):
            return False

    def _deribit_positioning_snapshots(
        self, entity_keys: list[str] | None, interval: str | None
    ) -> list[dict]:
        now_iso = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
        rows: list[dict] = []
        for currency in self._deribit_target_currencies(entity_keys):
            try:
                summaries = self.deribit.get_book_summary_by_currency(currency)
            except Exception as exc:
                logger.warning(f"Deribit positioning fallback 失败 [{currency}]: {exc}")
                continue
            call_oi = 0.0
            put_oi = 0.0
            for s in summaries:
                name = s.get("instrument_name", "")
                oi = float(s.get("open_interest") or 0)
                if "-C" in name:
                    call_oi += oi
                elif "-P" in name:
                    put_oi += oi
            total_oi = call_oi + put_oi
            index_price = 0.0
            try:
                index_price = self.deribit.get_index_price(currency)
            except Exception:
                pass
            rows.append({
                "entity_key": currency,
                "observation_time": now_iso,
                "interval": interval or "1h",
                "call_open_interest_notional": call_oi * index_price,
                "put_open_interest_notional": put_oi * index_price,
                "total_open_interest_notional": total_oi * index_price,
                "quality_flag": "ok",
                "source_symbol": f"{currency}-DERIBIT-OI",
                "raw_payload_json": json.dumps({
                    "source": "deribit", "call_oi": call_oi, "put_oi": put_oi,
                }),
            })
        return rows

    def _deribit_relative_value_snapshots(
        self, entity_keys: list[str] | None, interval: str | None
    ) -> list[dict]:
        now_iso = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
        rows: list[dict] = []
        for currency in self._deribit_target_currencies(entity_keys):
            try:
                hist_vol = self.deribit.get_historical_volatility(currency)
                summaries = self.deribit.get_book_summary_by_currency(currency)
            except Exception as exc:
                logger.warning(f"Deribit RV fallback 失败 [{currency}]: {exc}")
                continue
            # 历史波动率: 取最近值
            rv_30d = None
            if hist_vol and len(hist_vol) > 0:
                latest_entry = hist_vol[-1]
                if isinstance(latest_entry, list) and len(latest_entry) >= 2:
                    rv_30d = float(latest_entry[1]) / 100
            # ATM IV
            ivs = [s["mark_iv"] for s in summaries if s.get("mark_iv") and s["mark_iv"] > 0]
            atm_iv_30d = sorted(ivs)[len(ivs) // 2] / 100 if ivs else None
            rows.append({
                "entity_key": currency,
                "observation_time": now_iso,
                "interval": interval or "1h",
                "realized_vol_30d": rv_30d,
                "atm_iv_30d": atm_iv_30d,
                "quality_flag": "ok",
                "source_symbol": f"{currency}-DERIBIT-RV",
                "raw_payload_json": json.dumps({
                    "source": "deribit", "rv_30d": rv_30d, "iv_30d": atm_iv_30d,
                }),
            })
        return rows

    def _deribit_strike_concentration_snapshots(
        self, entity_keys: list[str] | None, interval: str | None
    ) -> list[dict]:
        now_iso = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
        rows: list[dict] = []
        for currency in self._deribit_target_currencies(entity_keys):
            try:
                summaries = self.deribit.get_book_summary_by_currency(currency)
                index_price = self.deribit.get_index_price(currency)
            except Exception as exc:
                logger.warning(f"Deribit strike fallback 失败 [{currency}]: {exc}")
                continue
            if not index_price:
                continue
            # 找最大 OI 的 call/put strike
            max_call_oi, max_call_strike = 0.0, 0.0
            max_put_oi, max_put_strike = 0.0, 0.0
            total_oi = 0.0
            for s in summaries:
                name = s.get("instrument_name", "")
                oi = float(s.get("open_interest") or 0)
                total_oi += oi
                parts = name.split("-")
                if len(parts) >= 4:
                    try:
                        strike = float(parts[2])
                    except (ValueError, IndexError):
                        continue
                    if parts[3] == "C" and oi > max_call_oi:
                        max_call_oi, max_call_strike = oi, strike
                    elif parts[3] == "P" and oi > max_put_oi:
                        max_put_oi, max_put_strike = oi, strike
            rows.append({
                "entity_key": currency,
                "observation_time": now_iso,
                "interval": interval or "1h",
                "index_price": index_price,
                "call_wall_strike": max_call_strike,
                "put_wall_strike": max_put_strike,
                "quality_flag": "ok",
                "source_symbol": f"{currency}-DERIBIT-STRIKE",
                "raw_payload_json": json.dumps({
                    "source": "deribit",
                    "call_wall": max_call_strike,
                    "put_wall": max_put_strike,
                    "total_oi": total_oi,
                }),
            })
        return rows

    def _deribit_gamma_exposure_snapshots(
        self, entity_keys: list[str] | None, interval: str | None
    ) -> list[dict]:
        now_iso = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
        rows: list[dict] = []
        for currency in self._deribit_target_currencies(entity_keys):
            try:
                summaries = self.deribit.get_book_summary_by_currency(currency)
                index_price = self.deribit.get_index_price(currency)
            except Exception as exc:
                logger.warning(f"Deribit gamma fallback 失败 [{currency}]: {exc}")
                continue
            if not index_price:
                continue
            # 近似 gamma exposure: 基于 OI 和 strike 距离
            net_gamma = 0.0
            for s in summaries:
                name = s.get("instrument_name", "")
                oi = float(s.get("open_interest") or 0)
                parts = name.split("-")
                if len(parts) >= 4:
                    try:
                        strike = float(parts[2])
                    except (ValueError, IndexError):
                        continue
                    distance = (strike - index_price) / index_price
                    gamma_contrib = oi * max(0, 0.1 - abs(distance))
                    if parts[3] == "C":
                        net_gamma += gamma_contrib
                    else:
                        net_gamma -= gamma_contrib
            rows.append({
                "entity_key": currency,
                "observation_time": now_iso,
                "interval": interval or "1h",
                "net_gamma_exposure_usd": net_gamma * index_price,
                "quality_flag": "partial",
                "source_symbol": f"{currency}-DERIBIT-GAMMA",
                "raw_payload_json": json.dumps({
                    "source": "deribit", "net_gamma_approx": net_gamma,
                }),
            })
        return rows

    def _deribit_flow_activity_snapshots(
        self, entity_keys: list[str] | None, interval: str | None
    ) -> list[dict]:
        now_iso = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
        rows: list[dict] = []
        for currency in self._deribit_target_currencies(entity_keys):
            try:
                summaries = self.deribit.get_book_summary_by_currency(currency)
            except Exception as exc:
                logger.warning(f"Deribit flow fallback 失败 [{currency}]: {exc}")
                continue
            # 使用 volume 作为 flow 近似
            call_volume = 0.0
            put_volume = 0.0
            for s in summaries:
                name = s.get("instrument_name", "")
                vol = float(s.get("volume") or 0)
                if "-C" in name:
                    call_volume += vol
                elif "-P" in name:
                    put_volume += vol
            total_vol = call_volume + put_volume
            rows.append({
                "entity_key": currency,
                "observation_time": now_iso,
                "interval": interval or "1h",
                "call_buyer_premium_share": (
                    call_volume / total_vol if total_vol > 0 else 0.5
                ),
                "put_buyer_premium_share": (
                    put_volume / total_vol if total_vol > 0 else 0.5
                ),
                "quality_flag": "partial",
                "source_symbol": f"{currency}-DERIBIT-FLOW",
                "raw_payload_json": json.dumps({
                    "source": "deribit",
                    "call_vol": call_volume, "put_vol": put_volume,
                }),
            })
        return rows

    def _deribit_expiry_structure_snapshots(
        self, entity_keys: list[str] | None, interval: str | None
    ) -> list[dict]:
        now_iso = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
        rows: list[dict] = []
        for currency in self._deribit_target_currencies(entity_keys):
            try:
                summaries = self.deribit.get_book_summary_by_currency(currency)
            except Exception as exc:
                logger.warning(f"Deribit expiry fallback 失败 [{currency}]: {exc}")
                continue
            # 按到期分桶
            near_oi, mid_oi, far_oi = 0.0, 0.0, 0.0
            for s in summaries:
                name = s.get("instrument_name", "")
                oi = float(s.get("open_interest") or 0)
                if self._is_near_expiry(name, days=8):
                    near_oi += oi
                elif self._is_near_expiry(name, days=31):
                    mid_oi += oi
                else:
                    far_oi += oi
            total = near_oi + mid_oi + far_oi
            buckets = []
            if total > 0:
                buckets = [
                    {"bucket": "7d", "oi_share": near_oi / total},
                    {"bucket": "30d", "oi_share": mid_oi / total},
                    {"bucket": "90d+", "oi_share": far_oi / total},
                ]
            rows.append({
                "entity_key": currency,
                "observation_time": now_iso,
                "interval": interval or "1h",
                "buckets": buckets,
                "quality_flag": "ok",
                "source_symbol": f"{currency}-DERIBIT-EXPIRY",
                "raw_payload_json": json.dumps({
                    "source": "deribit", "near": near_oi,
                    "mid": mid_oi, "far": far_oi,
                }),
            })
        return rows

    def _deribit_hedge_pressure_snapshots(
        self, entity_keys: list[str] | None, interval: str | None
    ) -> list[dict]:
        now_iso = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
        rows: list[dict] = []
        for currency in self._deribit_target_currencies(entity_keys):
            try:
                summaries = self.deribit.get_book_summary_by_currency(currency)
                index_price = self.deribit.get_index_price(currency)
            except Exception as exc:
                logger.warning(f"Deribit hedge fallback 失败 [{currency}]: {exc}")
                continue
            # 近似 vanna/charm: 基于 OI 分布
            total_oi = sum(float(s.get("open_interest") or 0) for s in summaries)
            near_oi = sum(
                float(s.get("open_interest") or 0)
                for s in summaries
                if self._is_near_expiry(s.get("instrument_name", ""), days=8)
            )
            rows.append({
                "entity_key": currency,
                "observation_time": now_iso,
                "interval": interval or "1h",
                "near_expiry_gamma_share": (
                    near_oi / total_oi if total_oi > 0 else 0
                ),
                "quality_flag": "partial",
                "source_symbol": f"{currency}-DERIBIT-HEDGE",
                "raw_payload_json": json.dumps({
                    "source": "deribit",
                    "total_oi": total_oi, "near_oi": near_oi,
                }),
            })
        return rows
