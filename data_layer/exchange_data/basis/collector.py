import json
from datetime import datetime, timezone

from loguru import logger

from config.settings import EXCHANGE_DERIVATIVES_CONFIG, SCHEDULER_CONFIG
from data_layer.exchange_data.models import BasisSnapshot


class BasisCollector:
    """basis 计算器，基于 latest_tickers 和 latest_funding_rates 生成快照。"""

    MAX_COMPONENT_TIMESTAMP_GAP_SECONDS = max(
        15,
        int(SCHEDULER_CONFIG["ticker_interval"]) * 3,
    )

    def __init__(self, db, funding_collector=None):
        self.db = db
        self.funding_collector = funding_collector

    @staticmethod
    def _to_datetime(value: datetime | str | None) -> datetime | None:
        if value is None or value == "":
            return None
        if isinstance(value, datetime):
            dt = value
        else:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is not None:
            return dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt

    @staticmethod
    def _ensure_naive_utc(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is not None:
            return value.astimezone(timezone.utc).replace(tzinfo=None)
        return value

    @staticmethod
    def _basis_bps(mark_price: float | None, spot_price: float | None) -> float | None:
        if mark_price is None or spot_price in (None, 0):
            return None
        return (mark_price - spot_price) / spot_price * 10000

    @staticmethod
    def _utc_now_naive() -> datetime:
        return datetime.now(timezone.utc).replace(tzinfo=None)

    @classmethod
    def _component_timestamp_gap_seconds(
        cls,
        funding_timestamp: datetime,
        ticker_timestamp: datetime | None,
    ) -> tuple[float | None, str]:
        if ticker_timestamp is None:
            return None, "missing_ticker_timestamp"
        gap_seconds = round(
            abs((funding_timestamp - ticker_timestamp).total_seconds()),
            3,
        )
        if gap_seconds > cls.MAX_COMPONENT_TIMESTAMP_GAP_SECONDS:
            return gap_seconds, "wide"
        return gap_seconds, "ok"

    def fetch_snapshots(self) -> list[BasisSnapshot]:
        rows = self.db.fetch_all(
            """
            SELECT
                funding.symbol,
                funding.exchange,
                ticker.last_price AS spot_price,
                ticker.timestamp AS ticker_timestamp,
                funding.mark_price,
                funding.index_price,
                funding.funding_rate,
                funding.next_funding_time,
                funding.timestamp AS funding_timestamp
            FROM latest_funding_rates AS funding
            LEFT JOIN latest_tickers AS ticker
                ON funding.symbol = ticker.symbol
                AND funding.exchange = ticker.exchange
            """
        )
        snapshots: list[BasisSnapshot] = []
        for row in rows:
            spot_price = row["spot_price"]
            mark_price = row["mark_price"]
            try:
                timestamp = self._ensure_naive_utc(
                    self._to_datetime(row["funding_timestamp"])
                )
            except Exception as exc:
                logger.warning(
                    "basis funding_timestamp 解析失败 "
                    f"[{row['exchange']} {row['symbol']}]: {type(exc).__name__}: {exc}"
                )
                timestamp = None
            if timestamp is None:
                logger.warning(
                    "basis funding_timestamp 缺失，跳过该行 "
                    f"[{row['exchange']} {row['symbol']}]，避免把坏时间戳伪装成最新 basis。"
                )
                continue

            ticker_timestamp = None
            ticker_timestamp_status = "missing"
            try:
                ticker_timestamp = self._ensure_naive_utc(
                    self._to_datetime(row["ticker_timestamp"])
                )
            except Exception as exc:
                logger.warning(
                    "basis ticker_timestamp 解析失败 "
                    f"[{row['exchange']} {row['symbol']}]: {type(exc).__name__}: {exc}"
                )
                ticker_timestamp_status = "parse_error"
            else:
                if ticker_timestamp is not None:
                    ticker_timestamp_status = "ok"

            basis_bps = self._basis_bps(mark_price, spot_price)
            component_gap_seconds, component_gap_status = self._component_timestamp_gap_seconds(
                timestamp,
                ticker_timestamp,
            )
            try:
                next_funding_time = self._ensure_naive_utc(
                    self._to_datetime(row["next_funding_time"])
                )
                next_funding_time_status = (
                    "ok"
                    if next_funding_time is not None
                    else "missing"
                )
            except Exception as exc:
                logger.warning(
                    "basis next_funding_time 解析失败 "
                    f"[{row['exchange']} {row['symbol']}]: {type(exc).__name__}: {exc}"
                )
                next_funding_time = None
                next_funding_time_status = "parse_error"
            annualized_basis_bps = None
            annualization_status = "missing_basis_bps"
            hours_to_funding = None
            if basis_bps is None:
                annualization_status = "missing_basis_bps"
            elif next_funding_time is None:
                annualization_status = (
                    "invalid_next_funding_time"
                    if next_funding_time_status == "parse_error"
                    else "missing_next_funding_time"
                )
            elif next_funding_time <= timestamp:
                next_funding_time_status = "non_future"
                annualization_status = "non_future_next_funding_time"
            else:
                hours_to_funding = max((next_funding_time - timestamp).total_seconds() / 3600, 1.0)
                annualized_basis_bps = basis_bps * (24 * 365 / hours_to_funding)
                annualization_status = "ok"

            diagnostics = {
                "funding_timestamp_status": "ok",
                "ticker_timestamp_status": ticker_timestamp_status,
                "ticker_timestamp": (
                    ticker_timestamp.isoformat()
                    if ticker_timestamp is not None
                    else None
                ),
                "component_timestamp_gap_seconds": component_gap_seconds,
                "component_timestamp_gap_status": component_gap_status,
                "max_component_timestamp_gap_seconds": self.MAX_COMPONENT_TIMESTAMP_GAP_SECONDS,
                "next_funding_time_status": next_funding_time_status,
                "annualization_status": annualization_status,
                "hours_to_funding": hours_to_funding,
            }
            snapshots.append(
                BasisSnapshot(
                    symbol=str(row["symbol"]),
                    exchange=str(row["exchange"]),
                    market_type="linear_swap",
                    interval=EXCHANGE_DERIVATIVES_CONFIG["basis_interval"],
                    timestamp=timestamp,
                    spot_price=float(spot_price) if spot_price is not None else None,
                    mark_price=float(mark_price) if mark_price is not None else None,
                    index_price=float(row["index_price"]) if row["index_price"] is not None else None,
                    basis_abs=(
                        float(mark_price) - float(spot_price)
                        if mark_price is not None and spot_price is not None
                        else None
                    ),
                    basis_bps=basis_bps,
                    annualized_basis_bps=annualized_basis_bps,
                    funding_rate=float(row["funding_rate"]) if row["funding_rate"] is not None else None,
                    next_funding_time=next_funding_time,
                    raw_payload_json=json.dumps(
                        {
                            "source_row": dict(row),
                            "diagnostics": diagnostics,
                        },
                        ensure_ascii=False,
                        default=str,
                    ),
                )
            )
        return snapshots

    def save_to_db(self, snapshots: list[BasisSnapshot]):
        if not snapshots:
            return
        history_sql = """
            INSERT INTO basis_snapshots (
                symbol, exchange, market_type, interval, timestamp,
                spot_price, mark_price, index_price,
                basis_abs, basis_bps, annualized_basis_bps,
                funding_rate, next_funding_time, raw_payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol, exchange, market_type, interval, timestamp) DO UPDATE SET
                spot_price=excluded.spot_price,
                mark_price=excluded.mark_price,
                index_price=excluded.index_price,
                basis_abs=excluded.basis_abs,
                basis_bps=excluded.basis_bps,
                annualized_basis_bps=excluded.annualized_basis_bps,
                funding_rate=excluded.funding_rate,
                next_funding_time=excluded.next_funding_time,
                raw_payload_json=excluded.raw_payload_json
        """
        latest_sql = """
            INSERT INTO latest_basis_snapshots (
                symbol, exchange, market_type, interval, timestamp,
                spot_price, mark_price, index_price,
                basis_abs, basis_bps, annualized_basis_bps,
                funding_rate, next_funding_time, raw_payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol, exchange, market_type, interval) DO UPDATE SET
                timestamp=excluded.timestamp,
                spot_price=excluded.spot_price,
                mark_price=excluded.mark_price,
                index_price=excluded.index_price,
                basis_abs=excluded.basis_abs,
                basis_bps=excluded.basis_bps,
                annualized_basis_bps=excluded.annualized_basis_bps,
                funding_rate=excluded.funding_rate,
                next_funding_time=excluded.next_funding_time,
                raw_payload_json=excluded.raw_payload_json,
                updated_at=CURRENT_TIMESTAMP
            WHERE excluded.timestamp >= latest_basis_snapshots.timestamp
        """
        params = [
            (
                snapshot.symbol,
                snapshot.exchange,
                snapshot.market_type,
                snapshot.interval,
                snapshot.timestamp.isoformat(),
                snapshot.spot_price,
                snapshot.mark_price,
                snapshot.index_price,
                snapshot.basis_abs,
                snapshot.basis_bps,
                snapshot.annualized_basis_bps,
                snapshot.funding_rate,
                snapshot.next_funding_time.isoformat() if snapshot.next_funding_time else None,
                snapshot.raw_payload_json,
            )
            for snapshot in snapshots
        ]
        self.db.execute_many(history_sql, params)
        self.db.execute_many(latest_sql, params)
        self.db.commit()

    def collect(self) -> list[BasisSnapshot]:
        if self.funding_collector:
            try:
                self.funding_collector.collect()
            except Exception as exc:
                logger.warning(f"basis 前置 funding 采集失败: {exc}")
        snapshots = self.fetch_snapshots()
        if snapshots:
            self.save_to_db(snapshots)
        logger.info(f"basis 计算完成，共 {len(snapshots)} 条快照")
        return snapshots
