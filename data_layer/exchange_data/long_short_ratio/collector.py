"""多空比采集器 — 使用 ccxt 直接从交易所获取多空比数据。"""

import json
import time
from datetime import datetime, timezone

import requests
from loguru import logger

from config.settings import EXCHANGE_DERIVATIVES_CONFIG
from config.symbols import TARGET_EXCHANGES, TARGET_SYMBOLS
from data_layer.exchange_data.client import ExchangeClientManager, retry_on_failure
from data_layer.exchange_data.models import PositioningSnapshot


def _to_swap_symbol(symbol: str) -> str:
    base, quote = symbol.split("/", 1)
    return f"{base}/{quote}:{quote}"


class LongShortRatioCollector:
    """多空比采集器 — 通过 ccxt fetch_long_short_ratio_history 获取数据。"""

    def __init__(self, db, client_manager: ExchangeClientManager | None = None):
        self.db = db
        self.manager = client_manager or ExchangeClientManager()

    def _fetch_okx_ls_ratio_native(self, symbol: str) -> list[dict]:
        """通过 OKX 公开 REST API 获取多空比数据。"""
        base = symbol.split("/")[0]
        url = "https://www.okx.com/api/v5/rubik/stat/contracts/long-short-account-ratio"
        params = {"ccy": base, "period": "1H"}
        try:
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") != "0":
                logger.warning(f"[okx] 多空比 API 返回错误: {data.get('msg')}")
                return []
            results = []
            for item in data.get("data", []):
                # OKX returns [ts_ms, longShortRatio] as string arrays
                ts_ms = int(item[0])
                ls_ratio = float(item[1])
                long_ratio = ls_ratio / (1 + ls_ratio) if ls_ratio > 0 else 0
                short_ratio = 1 - long_ratio
                results.append({
                    "timestamp": ts_ms,
                    "longShortRatio": ls_ratio,
                    "longAccount": long_ratio,
                    "shortAccount": short_ratio,
                })
            return results
        except Exception as exc:
            logger.warning(f"[okx] 原生多空比 API 失败 {base}: {exc}")
            return []

    @retry_on_failure
    def _fetch_exchange_ls_ratio(
        self, exchange_name: str, symbol: str, since_ms: int
    ) -> list[dict]:
        client = self.manager.get_client(exchange_name, market_type="swap")
        swap_symbol = _to_swap_symbol(symbol)
        try:
            return client.fetch_long_short_ratio_history(
                swap_symbol, timeframe="1h", since=since_ms, limit=50
            )
        except AttributeError:
            if exchange_name == "okx":
                return self._fetch_okx_ls_ratio_native(symbol)
            logger.debug(f"[{exchange_name}] fetch_long_short_ratio_history 不支持")
            return []
        except Exception as exc:
            if exchange_name == "okx":
                logger.debug(f"[okx] ccxt 多空比失败，回退原生 API: {exc}")
                return self._fetch_okx_ls_ratio_native(symbol)
            logger.warning(
                f"[{exchange_name}] 多空比获取失败 {swap_symbol}: {exc}"
            )
            return []

    def fetch_snapshots(self) -> list[PositioningSnapshot]:
        """从所有交易所获取多空比数据。"""
        now_ms = int(time.time() * 1000)
        since_ms = now_ms - 48 * 3600_000  # 回溯 48 小时
        interval_str = EXCHANGE_DERIVATIVES_CONFIG.get("positioning_interval", "1h")
        snapshots: list[PositioningSnapshot] = []

        for exchange_name in TARGET_EXCHANGES:
            for symbol in TARGET_SYMBOLS:
                raw = self._fetch_exchange_ls_ratio(exchange_name, symbol, since_ms)
                if not raw:
                    continue
                for entry in raw:
                    ts = entry.get("timestamp")
                    if isinstance(ts, (int, float)):
                        dt = datetime.fromtimestamp(
                            ts / 1000, tz=timezone.utc
                        ).replace(tzinfo=None)
                    elif isinstance(ts, str):
                        text = ts.replace("Z", "+00:00")
                        dt = datetime.fromisoformat(text).replace(tzinfo=None)
                    else:
                        continue

                    long_ratio = float(entry.get("longAccount", 0) or 0)
                    short_ratio = float(entry.get("shortAccount", 0) or 0)
                    ls_ratio = float(
                        entry.get("longShortRatio")
                        or entry.get("longAccount", 0) or 0
                    )
                    if long_ratio == 0 and ls_ratio > 0:
                        long_ratio = ls_ratio / (1 + ls_ratio)
                        short_ratio = 1 - long_ratio

                    snapshots.append(PositioningSnapshot(
                        symbol=symbol,
                        exchange=exchange_name,
                        market_type="linear_swap",
                        ratio_scope="accounts",
                        interval=interval_str,
                        timestamp=dt,
                        long_ratio=long_ratio if long_ratio else None,
                        short_ratio=short_ratio if short_ratio else None,
                        long_short_ratio=ls_ratio if ls_ratio else None,
                        top_trader_long_ratio=None,
                        top_trader_short_ratio=None,
                        raw_payload_json=json.dumps(
                            entry, ensure_ascii=False, default=str
                        ),
                    ))
                time.sleep(0.2)
        return snapshots

    def save_to_db(self, snapshots: list[PositioningSnapshot]):
        if not snapshots:
            return
        history_sql = """
            INSERT INTO positioning_snapshots (
                symbol, exchange, market_type, ratio_scope, interval, timestamp,
                long_ratio, short_ratio, long_short_ratio,
                top_trader_long_ratio, top_trader_short_ratio, raw_payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol, exchange, market_type, ratio_scope, interval, timestamp)
            DO UPDATE SET
                long_ratio=excluded.long_ratio,
                short_ratio=excluded.short_ratio,
                long_short_ratio=excluded.long_short_ratio,
                top_trader_long_ratio=excluded.top_trader_long_ratio,
                top_trader_short_ratio=excluded.top_trader_short_ratio,
                raw_payload_json=excluded.raw_payload_json
        """
        latest_sql = """
            INSERT INTO latest_positioning_snapshots (
                symbol, exchange, market_type, ratio_scope, interval, timestamp,
                long_ratio, short_ratio, long_short_ratio,
                top_trader_long_ratio, top_trader_short_ratio, raw_payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol, exchange, market_type, ratio_scope, interval)
            DO UPDATE SET
                timestamp=excluded.timestamp,
                long_ratio=excluded.long_ratio,
                short_ratio=excluded.short_ratio,
                long_short_ratio=excluded.long_short_ratio,
                top_trader_long_ratio=excluded.top_trader_long_ratio,
                top_trader_short_ratio=excluded.top_trader_short_ratio,
                raw_payload_json=excluded.raw_payload_json,
                updated_at=CURRENT_TIMESTAMP
            WHERE excluded.timestamp >= latest_positioning_snapshots.timestamp
        """
        params = [
            (
                s.symbol, s.exchange, s.market_type, s.ratio_scope, s.interval,
                s.timestamp.isoformat(), s.long_ratio, s.short_ratio,
                s.long_short_ratio, s.top_trader_long_ratio,
                s.top_trader_short_ratio, s.raw_payload_json,
            )
            for s in snapshots
        ]
        self.db.execute_many(history_sql, params)
        self.db.execute_many(latest_sql, params)
        self.db.commit()

    def collect(self) -> list[PositioningSnapshot]:
        snapshots = self.fetch_snapshots()
        if snapshots:
            self.save_to_db(snapshots)
        return snapshots
