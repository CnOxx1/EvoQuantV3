import json
from collections import defaultdict
from datetime import datetime, timezone

import ccxt
from loguru import logger

from config.settings import EXCHANGE_DERIVATIVES_CONFIG
from config.symbols import TARGET_EXCHANGES, TARGET_SYMBOLS
from data_layer.exchange_data.client import ExchangeClientManager, retry_on_failure
from data_layer.exchange_data.models import TradeFlowBar


class TradesCollector:
    """最近成交与主动买卖流聚合采集器。"""

    def __init__(self, client_manager: ExchangeClientManager, db):
        self.client_manager = client_manager
        self.db = db

    @staticmethod
    def _floor_time(dt: datetime, interval: str) -> datetime:
        if interval.endswith("m"):
            minutes = max(int(interval[:-1] or "1"), 1)
            floored_minute = (dt.minute // minutes) * minutes
            return dt.replace(second=0, microsecond=0, minute=floored_minute)
        if interval.endswith("h"):
            hours = max(int(interval[:-1] or "1"), 1)
            floored_hour = (dt.hour // hours) * hours
            return dt.replace(minute=0, second=0, microsecond=0, hour=floored_hour)
        return dt.replace(second=0, microsecond=0)

    @staticmethod
    def _to_swap_symbol(symbol: str) -> str:
        if ":" not in symbol:
            quote = symbol.split("/")[1] if "/" in symbol else "USDT"
            return f"{symbol}:{quote}"
        return symbol

    @staticmethod
    def _safe_float(value) -> float | None:
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _parse_trade_timestamp(value) -> datetime | None:
        if value is None or value == "":
            return None
        try:
            numeric_timestamp = float(value)
        except (TypeError, ValueError):
            return None
        return datetime.fromtimestamp(
            numeric_timestamp / 1000,
            tz=timezone.utc,
        ).replace(tzinfo=None)

    @staticmethod
    def _normalize_trade_side(value) -> str | None:
        side = str(value or "").strip().lower()
        if side in {"buy", "sell"}:
            return side
        return None

    @classmethod
    def _trade_notional(cls, trade: dict) -> float | None:
        cost = cls._safe_float(trade.get("cost"))
        if cost is not None:
            return cost if cost >= 0 else None
        price = cls._safe_float(trade.get("price"))
        amount = cls._safe_float(trade.get("amount"))
        if price is None or amount is None:
            return None
        notional = price * amount
        return notional if notional >= 0 else None

    @retry_on_failure
    def _fetch_trades(
        self,
        exchange_name: str,
        symbol: str,
        *,
        market_type: str = "spot",
    ) -> list[dict]:
        normalized_market_type = (
            "swap"
            if market_type in {"swap", "linear_swap", "perp", "perpetual"}
            else "spot"
        )
        client = self.client_manager.get_client(
            exchange_name,
            market_type=normalized_market_type,
        )
        if not client.markets:
            client.load_markets()
        fetch_symbol = (
            self._to_swap_symbol(symbol)
            if normalized_market_type == "swap"
            else symbol
        )
        return client.fetch_trades(
            fetch_symbol,
            limit=EXCHANGE_DERIVATIVES_CONFIG["trade_fetch_limit"],
        )

    def fetch_trade_flow_bars(self) -> list[TradeFlowBar]:
        interval = EXCHANGE_DERIVATIVES_CONFIG["trade_bar_interval"]
        bars: list[TradeFlowBar] = []
        for exchange_name in TARGET_EXCHANGES:
            for symbol in TARGET_SYMBOLS:
                for source_market_type, storage_market_type in (
                    ("spot", "spot"),
                    ("swap", "linear_swap"),
                ):
                    try:
                        raw_trades = self._fetch_trades(
                            exchange_name,
                            symbol,
                            market_type=source_market_type,
                        )
                    except (ccxt.BadSymbol, ccxt.NotSupported, ccxt.ExchangeError) as exc:
                        logger.warning(
                            f"成交接口不可用 [{exchange_name}] {symbol} "
                            f"[{storage_market_type}]: {exc}"
                        )
                        continue
                    except Exception as exc:
                        logger.error(
                            f"成交采集失败 [{exchange_name}] {symbol} "
                            f"[{storage_market_type}]: {exc}"
                        )
                        continue
                    grouped: dict[datetime, list[dict]] = defaultdict(list)
                    for trade in raw_trades:
                        dt = self._parse_trade_timestamp(trade.get("timestamp"))
                        if dt is None:
                            continue
                        grouped[self._floor_time(dt, interval)].append(trade)
                    for open_time, trades in grouped.items():
                        raw_trade_count = len(trades)
                        trade_count = 0
                        buy_trade_count = 0
                        sell_trade_count = 0
                        buy_notional = 0.0
                        sell_notional = 0.0
                        largest_trade_notional = 0.0
                        excluded_missing_side_count = 0
                        excluded_missing_notional_count = 0
                        for trade in trades:
                            side = self._normalize_trade_side(trade.get("side"))
                            if side is None:
                                excluded_missing_side_count += 1
                                continue
                            notional = self._trade_notional(trade)
                            if notional is None:
                                excluded_missing_notional_count += 1
                                continue

                            trade_count += 1
                            largest_trade_notional = max(largest_trade_notional, notional)
                            if side == "buy":
                                buy_trade_count += 1
                                buy_notional += notional
                            elif side == "sell":
                                sell_trade_count += 1
                                sell_notional += notional
                        if trade_count <= 0:
                            logger.warning(
                                "trade_flow bar 缺少可用成交方向/成交额，跳过 "
                                f"[{exchange_name}] {symbol} [{storage_market_type}] {open_time.isoformat()}"
                            )
                            continue
                        bars.append(
                            TradeFlowBar(
                                symbol=symbol,
                                exchange=exchange_name,
                                market_type=storage_market_type,
                                interval=interval,
                                open_time=open_time,
                                trade_count=trade_count,
                                buy_trade_count=buy_trade_count,
                                sell_trade_count=sell_trade_count,
                                buy_notional=buy_notional,
                                sell_notional=sell_notional,
                                aggressive_buy_notional=buy_notional,
                                aggressive_sell_notional=sell_notional,
                                net_taker_notional=buy_notional - sell_notional,
                                cvd=buy_notional - sell_notional,
                                avg_trade_notional=(
                                    (buy_notional + sell_notional) / trade_count
                                    if trade_count
                                    else 0.0
                                ),
                                largest_trade_notional=largest_trade_notional,
                                raw_payload_json=json.dumps(
                                    {
                                        "trades": trades,
                                        "diagnostics": {
                                            "raw_trade_count": raw_trade_count,
                                            "usable_trade_count": trade_count,
                                            "excluded_trade_count": (
                                                raw_trade_count - trade_count
                                            ),
                                            "excluded_missing_side_count": (
                                                excluded_missing_side_count
                                            ),
                                            "excluded_missing_notional_count": (
                                                excluded_missing_notional_count
                                            ),
                                        },
                                    },
                                    ensure_ascii=False,
                                    separators=(",", ":"),
                                ),
                            )
                        )
        return bars

    def save_to_db(self, bars: list[TradeFlowBar]):
        if not bars:
            return
        history_sql = """
            INSERT INTO trade_flow_bars (
                symbol, exchange, market_type, interval, open_time,
                trade_count, buy_trade_count, sell_trade_count,
                buy_notional, sell_notional,
                aggressive_buy_notional, aggressive_sell_notional,
                net_taker_notional, cvd, avg_trade_notional,
                largest_trade_notional, collected_at, raw_payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol, exchange, market_type, interval, open_time) DO UPDATE SET
                trade_count=excluded.trade_count,
                buy_trade_count=excluded.buy_trade_count,
                sell_trade_count=excluded.sell_trade_count,
                buy_notional=excluded.buy_notional,
                sell_notional=excluded.sell_notional,
                aggressive_buy_notional=excluded.aggressive_buy_notional,
                aggressive_sell_notional=excluded.aggressive_sell_notional,
                net_taker_notional=excluded.net_taker_notional,
                cvd=excluded.cvd,
                avg_trade_notional=excluded.avg_trade_notional,
                largest_trade_notional=excluded.largest_trade_notional,
                collected_at=excluded.collected_at,
                raw_payload_json=excluded.raw_payload_json,
                updated_at=CURRENT_TIMESTAMP
        """
        latest_sql = """
            INSERT INTO latest_trade_flow_bars (
                symbol, exchange, market_type, interval, open_time,
                trade_count, buy_trade_count, sell_trade_count,
                buy_notional, sell_notional,
                aggressive_buy_notional, aggressive_sell_notional,
                net_taker_notional, cvd, avg_trade_notional,
                largest_trade_notional, collected_at, raw_payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol, exchange, market_type, interval) DO UPDATE SET
                open_time=excluded.open_time,
                trade_count=excluded.trade_count,
                buy_trade_count=excluded.buy_trade_count,
                sell_trade_count=excluded.sell_trade_count,
                buy_notional=excluded.buy_notional,
                sell_notional=excluded.sell_notional,
                aggressive_buy_notional=excluded.aggressive_buy_notional,
                aggressive_sell_notional=excluded.aggressive_sell_notional,
                net_taker_notional=excluded.net_taker_notional,
                cvd=excluded.cvd,
                avg_trade_notional=excluded.avg_trade_notional,
                largest_trade_notional=excluded.largest_trade_notional,
                collected_at=excluded.collected_at,
                raw_payload_json=excluded.raw_payload_json,
                updated_at=CURRENT_TIMESTAMP
            WHERE excluded.open_time >= latest_trade_flow_bars.open_time
        """
        params = [
            (
                bar.symbol,
                bar.exchange,
                bar.market_type,
                bar.interval,
                bar.open_time.isoformat(),
                bar.trade_count,
                bar.buy_trade_count,
                bar.sell_trade_count,
                bar.buy_notional,
                bar.sell_notional,
                bar.aggressive_buy_notional,
                bar.aggressive_sell_notional,
                bar.net_taker_notional,
                bar.cvd,
                bar.avg_trade_notional,
                bar.largest_trade_notional,
                bar.collected_at.isoformat(),
                bar.raw_payload_json,
            )
            for bar in bars
        ]
        self.db.execute_many(history_sql, params)
        self.db.execute_many(latest_sql, params)
        self.db.commit()

    def collect(self) -> list[TradeFlowBar]:
        bars = self.fetch_trade_flow_bars()
        if bars:
            self.save_to_db(bars)
        logger.info(f"成交/主动买卖流采集完成，共 {len(bars)} 条 bar")
        return bars
