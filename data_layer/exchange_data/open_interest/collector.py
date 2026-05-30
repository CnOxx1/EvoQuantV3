import json
from datetime import datetime, timedelta, timezone

import ccxt
from loguru import logger

from config.settings import EXCHANGE_DERIVATIVES_CONFIG
from config.symbols import TARGET_EXCHANGES, TARGET_SYMBOLS
from data_layer.exchange_data.client import ExchangeClientManager, retry_on_failure
from data_layer.exchange_data.models import OpenInterestSnapshot
from data_layer.exchange_data.normalized_derivatives import NormalizedDerivativesClient


class OpenInterestCollector:
    """持仓量采集器。"""

    def __init__(self, client_manager: ExchangeClientManager, db):
        self.client_manager = client_manager
        self.db = db
        self.normalized_client = NormalizedDerivativesClient()

    @staticmethod
    def _to_swap_symbol(symbol: str) -> str:
        if ":" not in symbol:
            quote = symbol.split("/")[1] if "/" in symbol else "USDT"
            return f"{symbol}:{quote}"
        return symbol

    @retry_on_failure
    def _fetch_open_interest(self, exchange_name: str, symbol: str) -> dict | None:
        client = self.client_manager.get_client(exchange_name, market_type="swap")
        method = getattr(client, "fetch_open_interest", None)
        if not callable(method):
            return None
        return method(self._to_swap_symbol(symbol))

    @staticmethod
    def _parse_time(value) -> datetime | None:
        if isinstance(value, datetime):
            dt = value
        elif value is None or value == "":
            return None
        elif isinstance(value, (int, float)):
            dt = datetime.fromtimestamp(float(value) / 1000, tz=timezone.utc)
        else:
            text = str(value).strip()
            if text.endswith("Z"):
                text = f"{text[:-1]}+00:00"
            dt = datetime.fromisoformat(text)
        if dt.tzinfo is not None:
            return dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt

    def _snapshot_from_raw(self, exchange_name: str, symbol: str, raw: dict) -> OpenInterestSnapshot:
        open_interest_contracts = raw.get("openInterestAmount")
        if open_interest_contracts is None:
            open_interest_contracts = raw.get("openInterest")
        open_interest_usd = raw.get("openInterestValue")
        if open_interest_usd is None:
            open_interest_usd = raw.get("openInterestUsd")
        timestamp = self._parse_time(raw.get("timestamp"))
        if timestamp is None:
            raise ValueError("missing open interest timestamp")
        return OpenInterestSnapshot(
            symbol=symbol,
            exchange=exchange_name,
            market_type="linear_swap",
            interval=EXCHANGE_DERIVATIVES_CONFIG["open_interest_interval"],
            timestamp=timestamp,
            open_interest_contracts=(
                float(open_interest_contracts)
                if open_interest_contracts is not None
                else None
            ),
            open_interest_usd=(
                float(open_interest_usd)
                if open_interest_usd is not None
                else None
            ),
            raw_payload_json=json.dumps(raw, ensure_ascii=False, separators=(",", ":")),
        )

    @staticmethod
    def _reference_value_from_row(row) -> float | None:
        if row is None:
            return None
        open_interest_usd = row["open_interest_usd"]
        if open_interest_usd is not None:
            return float(open_interest_usd)
        open_interest_contracts = row["open_interest_contracts"]
        if open_interest_contracts is not None:
            return float(open_interest_contracts)
        return None

    @staticmethod
    def _reference_value_from_snapshot(snapshot: OpenInterestSnapshot) -> float | None:
        if snapshot.open_interest_usd is not None:
            return float(snapshot.open_interest_usd)
        if snapshot.open_interest_contracts is not None:
            return float(snapshot.open_interest_contracts)
        return None

    def _lookup_baseline_value(
        self,
        snapshot: OpenInterestSnapshot,
        *,
        lookback: timedelta,
    ) -> float | None:
        row = self.db.fetch_one(
            """
            SELECT open_interest_contracts, open_interest_usd
            FROM open_interest_snapshots
            WHERE symbol = ?
              AND exchange = ?
              AND market_type = ?
              AND interval = ?
              AND timestamp <= ?
            ORDER BY timestamp DESC
            LIMIT 1
            """,
            (
                snapshot.symbol,
                snapshot.exchange,
                snapshot.market_type,
                snapshot.interval,
                (snapshot.timestamp - lookback).isoformat(),
            ),
        )
        return self._reference_value_from_row(row)

    def _enrich_change_metrics(self, snapshots: list[OpenInterestSnapshot]):
        for snapshot in snapshots:
            current_value = self._reference_value_from_snapshot(snapshot)
            if current_value is None:
                continue
            baseline_5m = self._lookup_baseline_value(
                snapshot,
                lookback=timedelta(minutes=5),
            )
            baseline_1h = self._lookup_baseline_value(
                snapshot,
                lookback=timedelta(hours=1),
            )
            baseline_24h = self._lookup_baseline_value(
                snapshot,
                lookback=timedelta(hours=24),
            )
            snapshot.open_interest_change_5m = (
                current_value - baseline_5m
                if baseline_5m is not None
                else None
            )
            snapshot.open_interest_change_1h = (
                current_value - baseline_1h
                if baseline_1h is not None
                else None
            )
            snapshot.open_interest_change_24h = (
                current_value - baseline_24h
                if baseline_24h is not None
                else None
            )

    def _fetch_normalized_snapshots(self) -> list[OpenInterestSnapshot]:
        return []

    def fetch_snapshots(self) -> list[OpenInterestSnapshot]:
        snapshots: list[OpenInterestSnapshot] = []
        for exchange_name in TARGET_EXCHANGES:
            for symbol in TARGET_SYMBOLS:
                try:
                    raw = self._fetch_open_interest(exchange_name, symbol)
                    if raw:
                        snapshots.append(self._snapshot_from_raw(exchange_name, symbol, raw))
                except ValueError as exc:
                    logger.warning(
                        f"持仓量快照时间戳无效，跳过 [{exchange_name}] {symbol}: {exc}"
                    )
                except (ccxt.BadSymbol, ccxt.NotSupported, ccxt.ExchangeError) as exc:
                    logger.warning(f"持仓量接口不可用 [{exchange_name}] {symbol}: {exc}")
                except Exception as exc:
                    logger.error(f"持仓量采集失败 [{exchange_name}] {symbol}: {exc}")
        snapshots.extend(self._fetch_normalized_snapshots())
        return snapshots

    def save_to_db(self, snapshots: list[OpenInterestSnapshot]):
        if not snapshots:
            return
        self._enrich_change_metrics(snapshots)
        history_sql = """
            INSERT INTO open_interest_snapshots (
                symbol, exchange, market_type, interval, timestamp,
                open_interest_contracts, open_interest_usd,
                open_interest_change_5m, open_interest_change_1h, open_interest_change_24h,
                raw_payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol, exchange, market_type, interval, timestamp) DO UPDATE SET
                open_interest_contracts=excluded.open_interest_contracts,
                open_interest_usd=excluded.open_interest_usd,
                open_interest_change_5m=excluded.open_interest_change_5m,
                open_interest_change_1h=excluded.open_interest_change_1h,
                open_interest_change_24h=excluded.open_interest_change_24h,
                raw_payload_json=excluded.raw_payload_json
        """
        latest_sql = """
            INSERT INTO latest_open_interest_snapshots (
                symbol, exchange, market_type, interval, timestamp,
                open_interest_contracts, open_interest_usd,
                open_interest_change_5m, open_interest_change_1h, open_interest_change_24h,
                raw_payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol, exchange, market_type, interval) DO UPDATE SET
                timestamp=excluded.timestamp,
                open_interest_contracts=excluded.open_interest_contracts,
                open_interest_usd=excluded.open_interest_usd,
                open_interest_change_5m=excluded.open_interest_change_5m,
                open_interest_change_1h=excluded.open_interest_change_1h,
                open_interest_change_24h=excluded.open_interest_change_24h,
                raw_payload_json=excluded.raw_payload_json,
                updated_at=CURRENT_TIMESTAMP
            WHERE excluded.timestamp >= latest_open_interest_snapshots.timestamp
        """
        params = [
            (
                snapshot.symbol,
                snapshot.exchange,
                snapshot.market_type,
                snapshot.interval,
                snapshot.timestamp.isoformat(),
                snapshot.open_interest_contracts,
                snapshot.open_interest_usd,
                snapshot.open_interest_change_5m,
                snapshot.open_interest_change_1h,
                snapshot.open_interest_change_24h,
                snapshot.raw_payload_json,
            )
            for snapshot in snapshots
        ]
        self.db.execute_many(history_sql, params)
        self.db.execute_many(latest_sql, params)
        self.db.commit()

    def collect(self) -> list[OpenInterestSnapshot]:
        snapshots = self.fetch_snapshots()
        if snapshots:
            self.save_to_db(snapshots)
        logger.info(f"持仓量采集完成，共 {len(snapshots)} 条快照")
        return snapshots
