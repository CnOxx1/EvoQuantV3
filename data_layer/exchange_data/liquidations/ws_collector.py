"""WebSocket 实时清算流采集器 — Binance + Bybit 后台常驻进程。

用法：
    python -m data_layer.exchange_data.liquidations.ws_collector

功能：
    - 连接 Binance wss://fstream.binance.com/ws/!forceOrder@arr
    - 连接 Bybit wss://stream.bybit.com/v5/public/linear (liquidation topic)
    - 按 5 分钟窗口聚合清算事件
    - 每个窗口结束后写入 exchange_data.db
"""

import json
import threading
import time
from collections import defaultdict
from datetime import datetime, timezone

import websocket
from loguru import logger

from config.symbols import TARGET_SYMBOLS
from database.db_manager import DBManager
from data_layer.exchange_data.models import LiquidationBar


FLUSH_INTERVAL = 300  # 5 分钟聚合窗口
DB_PATH = "database/exchange_data.db"

# Binance symbol 映射: BTC/USDT -> BTCUSDT
_BINANCE_SYMBOLS = {s.replace("/", ""): s for s in TARGET_SYMBOLS}
# Bybit symbol 映射同上
_BYBIT_SYMBOLS = _BINANCE_SYMBOLS.copy()


def _align_ts(ts_ms: int) -> datetime:
    aligned = (ts_ms // 1000 // FLUSH_INTERVAL) * FLUSH_INTERVAL
    return datetime.fromtimestamp(aligned, tz=timezone.utc).replace(tzinfo=None)


class LiquidationAggregator:
    """线程安全的清算事件聚合器。"""

    def __init__(self):
        self._lock = threading.Lock()
        self._buckets: dict[tuple, dict] = defaultdict(lambda: {
            "long_notional": 0.0,
            "short_notional": 0.0,
            "long_count": 0,
            "short_count": 0,
            "max_single": 0.0,
        })

    def add(self, symbol: str, exchange: str, ts_ms: int, side: str,
            notional: float):
        open_time = _align_ts(ts_ms)
        key = (symbol, exchange, open_time)
        with self._lock:
            bucket = self._buckets[key]
            if side in ("buy", "long"):
                bucket["long_notional"] += notional
                bucket["long_count"] += 1
            else:
                bucket["short_notional"] += notional
                bucket["short_count"] += 1
            bucket["max_single"] = max(bucket["max_single"], notional)

    def flush(self) -> list[LiquidationBar]:
        """取出所有聚合数据并清空。"""
        with self._lock:
            snapshot = dict(self._buckets)
            self._buckets.clear()
        interval_str = "5m"
        bars: list[LiquidationBar] = []
        for (symbol, exchange, open_time), agg in snapshot.items():
            total = agg["long_notional"] + agg["short_notional"]
            if total == 0:
                continue
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


# ─── Binance WebSocket ───────────────────────────────────────────────

def _run_binance_ws(agg: LiquidationAggregator, stop_event: threading.Event):
    """Binance 全市场强平流: wss://fstream.binance.com/ws/!forceOrder@arr"""
    url = "wss://fstream.binance.com/ws/!forceOrder@arr"

    def on_message(ws, message):
        try:
            data = json.loads(message)
            order = data.get("o", data)
            raw_symbol = order.get("s", "")  # e.g. BTCUSDT
            symbol = _BINANCE_SYMBOLS.get(raw_symbol)
            if symbol is None:
                return
            ts_ms = int(order.get("T", 0))
            side = order.get("S", "").lower()  # BUY/SELL
            price = float(order.get("p", 0))
            qty = float(order.get("q", 0))
            notional = price * qty
            agg.add(symbol, "binance", ts_ms, side, notional)
        except Exception as exc:
            logger.debug(f"[binance-ws] 解析失败: {exc}")

    def on_error(ws, error):
        logger.warning(f"[binance-ws] 错误: {error}")

    def on_close(ws, code, msg):
        logger.info(f"[binance-ws] 连接关闭: {code} {msg}")

    while not stop_event.is_set():
        try:
            ws = websocket.WebSocketApp(
                url,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close,
            )
            ws.run_forever(ping_interval=30, ping_timeout=10)
        except Exception as exc:
            logger.warning(f"[binance-ws] 异常: {exc}")
        if not stop_event.is_set():
            time.sleep(5)  # 重连间隔


# ─── Bybit WebSocket ─────────────────────────────────────────────────

def _run_bybit_ws(agg: LiquidationAggregator, stop_event: threading.Event):
    """Bybit 清算流: wss://stream.bybit.com/v5/public/linear"""
    url = "wss://stream.bybit.com/v5/public/linear"
    topics = [f"liquidation.{s.replace('/', '')}" for s in TARGET_SYMBOLS]

    def on_open(ws):
        sub_msg = json.dumps({"op": "subscribe", "args": topics})
        ws.send(sub_msg)
        logger.info(f"[bybit-ws] 已订阅 {len(topics)} 个清算 topic")

    def on_message(ws, message):
        try:
            data = json.loads(message)
            if data.get("op") == "subscribe":
                return
            topic = data.get("topic", "")
            if not topic.startswith("liquidation."):
                return
            item = data.get("data", {})
            raw_symbol = item.get("symbol", "")
            symbol = _BYBIT_SYMBOLS.get(raw_symbol)
            if symbol is None:
                return
            ts_ms = int(item.get("updatedTime", 0))
            side = item.get("side", "").lower()  # Buy/Sell
            price = float(item.get("price", 0))
            qty = float(item.get("size", 0))
            notional = price * qty
            agg.add(symbol, "bybit", ts_ms, side, notional)
        except Exception as exc:
            logger.debug(f"[bybit-ws] 解析失败: {exc}")

    def on_error(ws, error):
        logger.warning(f"[bybit-ws] 错误: {error}")

    def on_close(ws, code, msg):
        logger.info(f"[bybit-ws] 连接关闭: {code} {msg}")

    while not stop_event.is_set():
        try:
            ws = websocket.WebSocketApp(
                url,
                on_open=on_open,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close,
            )
            ws.run_forever(ping_interval=20, ping_timeout=10)
        except Exception as exc:
            logger.warning(f"[bybit-ws] 异常: {exc}")
        if not stop_event.is_set():
            time.sleep(5)


# ─── DB 写入 & 主循环 ────────────────────────────────────────────────

def _save_bars(db: DBManager, bars: list[LiquidationBar]):
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
            long_liquidation_notional=
                liquidation_bars.long_liquidation_notional
                + excluded.long_liquidation_notional,
            short_liquidation_notional=
                liquidation_bars.short_liquidation_notional
                + excluded.short_liquidation_notional,
            long_liquidation_count=
                liquidation_bars.long_liquidation_count
                + excluded.long_liquidation_count,
            short_liquidation_count=
                liquidation_bars.short_liquidation_count
                + excluded.short_liquidation_count,
            total_liquidation_notional=
                liquidation_bars.total_liquidation_notional
                + excluded.total_liquidation_notional,
            max_single_liquidation_notional=MAX(
                liquidation_bars.max_single_liquidation_notional,
                excluded.max_single_liquidation_notional
            ),
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
    db.execute_many(history_sql, params)
    db.execute_many(latest_sql, params)
    db.commit()
    logger.info(
        f"[ws-liquidation] 写入 {len(bars)} 条 bars "
        f"(exchanges: {set(b.exchange for b in bars)})"
    )


def run(stop_event: threading.Event | None = None):
    """启动 WebSocket 清算采集主循环。"""
    if stop_event is None:
        stop_event = threading.Event()

    db = DBManager(DB_PATH)
    agg = LiquidationAggregator()

    # 启动 WebSocket 线程
    binance_thread = threading.Thread(
        target=_run_binance_ws, args=(agg, stop_event),
        daemon=True, name="binance-liq-ws",
    )
    bybit_thread = threading.Thread(
        target=_run_bybit_ws, args=(agg, stop_event),
        daemon=True, name="bybit-liq-ws",
    )
    binance_thread.start()
    bybit_thread.start()
    logger.info("[ws-liquidation] Binance + Bybit WebSocket 线程已启动")

    # 主循环：每 FLUSH_INTERVAL 秒刷新一次
    try:
        while not stop_event.is_set():
            stop_event.wait(timeout=FLUSH_INTERVAL)
            bars = agg.flush()
            if bars:
                try:
                    _save_bars(db, bars)
                except Exception as exc:
                    logger.error(f"[ws-liquidation] DB 写入失败: {exc}")
    except KeyboardInterrupt:
        logger.info("[ws-liquidation] 收到中断信号，正在退出...")
        stop_event.set()


if __name__ == "__main__":
    run()