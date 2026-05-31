"""清算聚合采集器 — 使用原生交易所 API 获取清算数据。"""

import json
import time
from datetime import datetime, timezone
from collections import defaultdict

import httpx
from loguru import logger

from config.settings import EXCHANGE_DERIVATIVES_CONFIG
from config.symbols import TARGET_EXCHANGES, TARGET_SYMBOLS
from data_layer.exchange_data.client import ExchangeClientManager, retry_on_failure
from data_layer.exchange_data.models import LiquidationBar


# 将 BTC/USDT 转为合约符号 BTC/USDT:USDT
def _to_swap_symbol(symbol: str) -> str:
    base, quote = symbol.split("/", 1)
    return f"{base}/{quote}:{quote}"


class LiquidationsCollector:
    """清算聚合采集器 — 通过原生 REST API 获取清算数据。"""

    INTERVAL_SECONDS = 300  # 5m 聚合窗口

    def __init__(self, db, client_manager: ExchangeClientManager | None = None):
        self.db = db
        self.manager = client_manager or ExchangeClientManager()

    @staticmethod
    def _align_to_interval(ts_ms: int, interval_s: int) -> datetime:
        """将毫秒时间戳对齐到 interval 窗口起始。"""
        aligned = (ts_ms // 1000 // interval_s) * interval_s
        return datetime.fromtimestamp(aligned, tz=timezone.utc).replace(tzinfo=None)

    def _fetch_okx_liquidations(self, symbol: str) -> list[dict]:
        """通过 OKX 公开 REST API 获取清算数据。"""
        base = symbol.split("/")[0]
        uly = f"{base}-USDT"
        url = "https://www.okx.com/api/v5/public/liquidation-orders"
        params = {"instType": "SWAP", "uly": uly, "state": "filled"}
        try:
            resp = httpx.get(url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") != "0":
                logger.debug(f"[okx] 清算 API 返回错误: {data.get('msg')}")
                return []
            results = []
            for item in data.get("data", []):
                for detail in item.get("details", []):
                    ts_ms = int(detail.get("ts", 0))
                    side = detail.get("side", "").lower()
                    sz = float(detail.get("sz", 0))
                    price = float(detail.get("bkPx", 0))
                    results.append({
                        "timestamp": ts_ms,
                        "side": side,
                        "amount": sz,
                        "price": price,
                    })
            return results
        except Exception as exc:
            logger.warning(f"[okx] 原生清算 API 失败 {uly}: {exc}")
            return []

    @retry_on_failure
    def _fetch_exchange_liquidations(
        self, exchange_name: str, symbol: str, since_ms: int
    ) -> list[dict]:
        if exchange_name == "okx":
            return self._fetch_okx_liquidations(symbol)
        client = self.manager.get_client(exchange_name, market_type="swap")
        swap_symbol = _to_swap_symbol(symbol)
        try:
            return client.fetch_liquidations(swap_symbol, since=since_ms, limit=100)
        except (AttributeError, Exception) as exc:
            logger.debug(f"[{exchange_name}] 清算数据不可用 {swap_symbol}: {exc}")
            return []

    def fetch_bars(self) -> list[LiquidationBar]:
        """从所有交易所获取清算数据并按 5m 窗口聚合。"""
        now_ms = int(time.time() * 1000)
        since_ms = now_ms - 3600_000  # 回溯 1 小时
        interval_s = self.INTERVAL_SECONDS
        interval_str = EXCHANGE_DERIVATIVES_CONFIG.get(
            "liquidation_bar_interval", "5m"
        )

        buckets: dict[tuple, dict] = defaultdict(lambda: {
            "long_notional": 0.0,
            "short_notional": 0.0,
            "long_count": 0,
            "short_count": 0,
            "max_single": 0.0,
        })

        for exchange_name in TARGET_EXCHANGES:
            for symbol in TARGET_SYMBOLS:
                raw = self._fetch_exchange_liquidations(
                    exchange_name, symbol, since_ms
                )
                if not raw:
                    continue
                for liq in raw:
                    ts = liq.get("timestamp") or liq.get("datetime")
                    if isinstance(ts, str):
                        ts = int(datetime.fromisoformat(
                            ts.replace("Z", "+00:00")
                        ).timestamp() * 1000)
                    if not isinstance(ts, (int, float)):
                        continue
                    if int(ts) < since_ms:
                        continue
                    open_time = self._align_to_interval(int(ts), interval_s)
                    side = str(liq.get("side") or "").lower()
                    amount = float(liq.get("amount") or 0)
                    price = float(liq.get("price") or 0)
                    notional = amount * price if price > 0 else 0

                    key = (symbol, exchange_name, open_time)
                    bucket = buckets[key]
                    if side == "buy" or side == "long":
                        bucket["long_notional"] += notional
                        bucket["long_count"] += 1
                    else:
                        bucket["short_notional"] += notional
                        bucket["short_count"] += 1
                    bucket["max_single"] = max(
                        bucket["max_single"], notional
                    )
                time.sleep(0.2)

        bars: list[LiquidationBar] = []
        for (symbol, exchange, open_time), agg in buckets.items():
            total = agg["long_notional"] + agg["short_notional"]
            bars.append(LiquidationBar(
                symbol=symbol,
                exchange=exchange,
                market_type="linear_swap",
                interval=interval_str,
                open_time=open_time,
                long_liquidation_notional=agg["long_notional"],
                short_liquidation_notional=agg["short_notional"],
                long_liquidation_count=agg["long_count"],
                short_liquidation_count=agg["short_count"],
                total_liquidation_notional=total,
                max_single_liquidation_notional=agg["max_single"],
                raw_payload_json=json.dumps(agg, ensure_ascii=False),
            ))
        return bars

    def save_to_db(self, bars: list[LiquidationBar]):
        if not bars:
            return
        history_sql = """
            INSERT INTO liquidation_bars (
                symbol, exchange, market_type, interval, open_time,
                long_liquidation_notional, short_liquidation_notional,
                long_liquidation_count, short_liquidation_count,
                total_liquidation_notional,
                max_single_liquidation_notional,
                collected_at, raw_payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol, exchange, market_type, interval, open_time)
            DO UPDATE SET
                long_liquidation_notional=excluded.long_liquidation_notional,
                short_liquidation_notional=excluded.short_liquidation_notional,
                long_liquidation_count=excluded.long_liquidation_count,
                short_liquidation_count=excluded.short_liquidation_count,
                total_liquidation_notional=excluded.total_liquidation_notional,
                max_single_liquidation_notional=excluded.max_single_liquidation_notional,
                collected_at=excluded.collected_at,
                raw_payload_json=excluded.raw_payload_json,
                updated_at=CURRENT_TIMESTAMP
        """
        latest_sql = """
            INSERT INTO latest_liquidation_bars (
                symbol, exchange, market_type, interval, open_time,
                long_liquidation_notional, short_liquidation_notional,
                long_liquidation_count, short_liquidation_count,
                total_liquidation_notional,
                max_single_liquidation_notional,
                collected_at, raw_payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol, exchange, market_type, interval)
            DO UPDATE SET
                open_time=excluded.open_time,
                long_liquidation_notional=excluded.long_liquidation_notional,
                short_liquidation_notional=excluded.short_liquidation_notional,
                long_liquidation_count=excluded.long_liquidation_count,
                short_liquidation_count=excluded.short_liquidation_count,
                total_liquidation_notional=excluded.total_liquidation_notional,
                max_single_liquidation_notional=excluded.max_single_liquidation_notional,
                collected_at=excluded.collected_at,
                raw_payload_json=excluded.raw_payload_json,
                updated_at=CURRENT_TIMESTAMP
            WHERE excluded.open_time >= latest_liquidation_bars.open_time
        """
        params = [
            (
                bar.symbol, bar.exchange, bar.market_type, bar.interval,
                bar.open_time.isoformat(),
                bar.long_liquidation_notional,
                bar.short_liquidation_notional,
                bar.long_liquidation_count, bar.short_liquidation_count,
                bar.total_liquidation_notional,
                bar.max_single_liquidation_notional,
                bar.collected_at.isoformat(), bar.raw_payload_json,
            )
            for bar in bars
        ]
        self.db.execute_many(history_sql, params)
        self.db.execute_many(latest_sql, params)
        self.db.commit()

    def collect(self) -> list[LiquidationBar]:
        bars = self.fetch_bars()
        if bars:
            self.save_to_db(bars)
        return bars
