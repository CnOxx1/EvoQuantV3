"""perpetual_basis_curve 服务层。"""

import statistics
from datetime import datetime, timezone, timedelta

from loguru import logger

from data_layer.perpetual_basis_curve.client import PerpetualBasisCurveClient


# 追踪的主要标的
TARGET_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"]


class PerpetualBasisCurveService:
    """永续合约基差曲线数据采集与分析服务。"""

    def __init__(self, client=None, db=None):
        if db is not None:
            self.db = db
        else:
            from database.router import DatabaseRouter, Domain
            self.db = DatabaseRouter().get_manager(Domain.MARKET_DATA)
        self.client = client or PerpetualBasisCurveClient()

    def init_storage(self):
        """初始化数据库表。"""
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS futures_term_structure (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                symbol TEXT NOT NULL,
                exchange TEXT NOT NULL,
                contract_type TEXT NOT NULL,
                expiry_date TEXT,
                price REAL NOT NULL,
                basis_pct REAL,
                annualized_basis_pct REAL,
                collected_at TEXT NOT NULL,
                UNIQUE(ts, symbol, exchange, contract_type)
            )
        """)
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS basis_curve_snapshot (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                symbol TEXT NOT NULL,
                curve_slope REAL,
                contango_backwardation TEXT,
                roll_yield_7d REAL,
                term_premium REAL,
                convexity REAL,
                collected_at TEXT NOT NULL,
                UNIQUE(ts, symbol)
            )
        """)
        self.db.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_term_structure_symbol_ts
            ON futures_term_structure(symbol, ts DESC)
        """)
        self.db.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_basis_snapshot_symbol_ts
            ON basis_curve_snapshot(symbol, ts DESC)
        """)
        self.db.conn.commit()
        logger.info("perpetual_basis_curve 存储初始化完成")

    def bootstrap(self, symbols: list[str] | None = None):
        """首次回填：拉取期限结构数据。"""
        symbols = symbols or TARGET_SYMBOLS
        logger.info(f"开始 bootstrap，目标: {symbols}")
        for symbol in symbols:
            self._collect_binance_term_structure(symbol)
            self._collect_okx_term_structure(symbol)
            self._collect_bybit_term_structure(symbol)
        self._compute_curve_snapshots(symbols)
        logger.info("bootstrap 完成")

    def collect_once(self, symbols: list[str] | None = None):
        """执行一次采集周期。"""
        symbols = symbols or TARGET_SYMBOLS
        for symbol in symbols:
            self._collect_binance_term_structure(symbol)
            self._collect_okx_term_structure(symbol)
            self._collect_bybit_term_structure(symbol)
        self._compute_curve_snapshots(symbols)
        logger.info(f"collect_once 完成，处理 {len(symbols)} 个标的")

    def _collect_binance_term_structure(self, symbol: str):
        """采集 Binance 永续+季度合约期限结构。"""
        now = datetime.now(timezone.utc)
        now_iso = now.strftime("%Y-%m-%dT%H:%M:%S")
        spot_price = self.client.fetch_spot_price(symbol)
        if spot_price is None:
            return
        # 永续合约
        perp_data = self.client.fetch_binance_futures_prices(symbol)
        for item in perp_data:
            mark_price = float(item.get("markPrice", 0))
            if mark_price <= 0:
                continue
            basis_pct = ((mark_price - spot_price) / spot_price) * 100
            self.db.conn.execute("""
                INSERT OR IGNORE INTO futures_term_structure
                (ts, symbol, exchange, contract_type, expiry_date, price,
                 basis_pct, annualized_basis_pct, collected_at)
                VALUES (?, ?, 'binance', 'perp', NULL, ?, ?, ?, ?)
            """, (now_iso, symbol, mark_price, basis_pct,
                  basis_pct * 365, now_iso))
        # 季度交割合约
        pair = symbol.replace("USDT", "USD")
        delivery_data = self.client.fetch_binance_delivery_prices(pair)
        for item in delivery_data:
            mark_price = float(item.get("markPrice", 0))
            if mark_price <= 0:
                continue
            contract_symbol = item.get("symbol", "")
            if "PERP" in contract_symbol.upper():
                contract_type = "perp"
                expiry = None
            elif "_" in contract_symbol:
                parts = contract_symbol.split("_")
                expiry = parts[-1] if len(parts) > 1 else None
                contract_type = "quarterly"
            else:
                contract_type = "quarterly"
                expiry = None
            basis_pct = ((mark_price - spot_price) / spot_price) * 100
            days_to_expiry = self._days_to_expiry(expiry)
            ann_basis = (basis_pct / days_to_expiry * 365) if days_to_expiry > 0 else basis_pct * 365
            self.db.conn.execute("""
                INSERT OR IGNORE INTO futures_term_structure
                (ts, symbol, exchange, contract_type, expiry_date, price,
                 basis_pct, annualized_basis_pct, collected_at)
                VALUES (?, ?, 'binance', ?, ?, ?, ?, ?, ?)
            """, (now_iso, symbol, contract_type, expiry, mark_price,
                  basis_pct, ann_basis, now_iso))
        self.db.conn.commit()

    def _collect_okx_term_structure(self, symbol: str):
        """采集 OKX 期货合约期限结构。"""
        now = datetime.now(timezone.utc)
        now_iso = now.strftime("%Y-%m-%dT%H:%M:%S")
        spot_price = self.client.fetch_spot_price(symbol)
        if spot_price is None:
            return
        futures_data = self.client.fetch_okx_futures_prices()
        base = symbol.replace("USDT", "").upper()
        for item in futures_data:
            inst_id = item.get("instId", "")
            if not inst_id.startswith(f"{base}-"):
                continue
            last_price = float(item.get("last", 0))
            if last_price <= 0:
                continue
            parts = inst_id.split("-")
            if len(parts) >= 3:
                expiry = parts[-1]
                contract_type = "quarterly" if len(expiry) == 6 else "bi_quarterly"
            else:
                contract_type = "perp"
                expiry = None
            basis_pct = ((last_price - spot_price) / spot_price) * 100
            days_to_expiry = self._days_to_expiry(expiry)
            ann_basis = (basis_pct / days_to_expiry * 365) if days_to_expiry > 0 else basis_pct * 365
            self.db.conn.execute("""
                INSERT OR IGNORE INTO futures_term_structure
                (ts, symbol, exchange, contract_type, expiry_date, price,
                 basis_pct, annualized_basis_pct, collected_at)
                VALUES (?, ?, 'okx', ?, ?, ?, ?, ?, ?)
            """, (now_iso, symbol, contract_type, expiry, last_price,
                  basis_pct, ann_basis, now_iso))
        self.db.conn.commit()

    def _collect_bybit_term_structure(self, symbol: str):
        """采集 Bybit 期货合约期限结构。"""
        now = datetime.now(timezone.utc)
        now_iso = now.strftime("%Y-%m-%dT%H:%M:%S")
        spot_price = self.client.fetch_spot_price(symbol)
        if spot_price is None:
            return
        futures_data = self.client.fetch_bybit_futures_prices()
        for item in futures_data:
            item_symbol = item.get("symbol", "")
            if not item_symbol.startswith(symbol.replace("USDT", "")):
                continue
            if "USDT" not in item_symbol:
                continue
            last_price = float(item.get("lastPrice", 0))
            if last_price <= 0:
                continue
            delivery_time = item.get("deliveryTime", "")
            if delivery_time == "" or delivery_time == "0":
                contract_type = "perp"
                expiry = None
            else:
                contract_type = "quarterly"
                expiry = delivery_time
            basis_pct = ((last_price - spot_price) / spot_price) * 100
            days_to_expiry = self._days_to_expiry(expiry)
            ann_basis = (basis_pct / days_to_expiry * 365) if days_to_expiry > 0 else basis_pct * 365
            self.db.conn.execute("""
                INSERT OR IGNORE INTO futures_term_structure
                (ts, symbol, exchange, contract_type, expiry_date, price,
                 basis_pct, annualized_basis_pct, collected_at)
                VALUES (?, ?, 'bybit', ?, ?, ?, ?, ?, ?)
            """, (now_iso, symbol, contract_type, expiry, last_price,
                  basis_pct, ann_basis, now_iso))
        self.db.conn.commit()

    @staticmethod
    def _days_to_expiry(expiry_str: str | None) -> float:
        """计算到期天数。"""
        if not expiry_str:
            return 0
        try:
            # 尝试解析 YYMMDD 格式
            if len(expiry_str) == 6:
                exp_date = datetime.strptime(expiry_str, "%y%m%d").replace(tzinfo=timezone.utc)
            # 尝试解析时间戳（毫秒）
            elif expiry_str.isdigit() and len(expiry_str) > 8:
                exp_date = datetime.fromtimestamp(int(expiry_str) / 1000, tz=timezone.utc)
            else:
                return 0
            delta = exp_date - datetime.now(timezone.utc)
            return max(delta.days, 1)
        except (ValueError, OSError):
            return 0

    def _compute_curve_snapshots(self, symbols: list[str]):
        """计算基差曲线快照指标。"""
        now = datetime.now(timezone.utc)
        now_iso = now.strftime("%Y-%m-%dT%H:%M:%S")

        for symbol in symbols:
            cursor = self.db.conn.execute("""
                SELECT contract_type, basis_pct, annualized_basis_pct, expiry_date
                FROM futures_term_structure
                WHERE symbol = ? AND ts >= ?
                ORDER BY basis_pct ASC
            """, (symbol, (now - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%S")))
            rows = cursor.fetchall()
            if not rows:
                continue

            basis_values = [r[1] for r in rows if r[1] is not None]
            ann_values = [r[2] for r in rows if r[2] is not None]
            perp_basis = [r[1] for r in rows if r[0] == "perp" and r[1] is not None]
            quarterly_basis = [r[1] for r in rows if r[0] == "quarterly" and r[1] is not None]

            # 曲线斜率：远期 - 近期基差
            if quarterly_basis and perp_basis:
                curve_slope = statistics.mean(quarterly_basis) - statistics.mean(perp_basis)
            elif len(basis_values) >= 2:
                curve_slope = basis_values[-1] - basis_values[0]
            else:
                curve_slope = 0.0

            # 判断 contango/backwardation
            avg_basis = statistics.mean(basis_values) if basis_values else 0
            if avg_basis > 0.05:
                structure = "contango"
            elif avg_basis < -0.05:
                structure = "backwardation"
            else:
                structure = "flat"

            # Roll yield 估算（7天）
            roll_yield_7d = (statistics.mean(ann_values) / 365 * 7) if ann_values else 0.0

            # 期限溢价
            term_premium = curve_slope * 4 if curve_slope else 0.0

            # 凸性（基差值的标准差）
            convexity = statistics.stdev(basis_values) if len(basis_values) >= 2 else 0.0

            self.db.conn.execute("""
                INSERT OR REPLACE INTO basis_curve_snapshot
                (ts, symbol, curve_slope, contango_backwardation,
                 roll_yield_7d, term_premium, convexity, collected_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (now_iso, symbol, round(curve_slope, 6), structure,
                  round(roll_yield_7d, 6), round(term_premium, 6),
                  round(convexity, 6), now_iso))
        self.db.conn.commit()

    def load_latest_context_bundle(self, symbols: list[str] | None = None) -> dict:
        """输出 AI 可读的基差曲线上下文 bundle。

        包含：
        - 当前期限结构形态（contango/backwardation/flat）
        - 曲线斜率变化趋势
        - Roll yield 估算
        - 期限溢价异常检测
        """
        symbols = symbols or TARGET_SYMBOLS
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

        placeholders = ",".join("?" * len(symbols))
        cursor = self.db.conn.execute(f"""
            SELECT symbol, curve_slope, contango_backwardation,
                   roll_yield_7d, term_premium, convexity, ts
            FROM basis_curve_snapshot
            WHERE symbol IN ({placeholders})
            ORDER BY ts DESC
        """, tuple(symbols))
        rows = cursor.fetchall()

        if not rows:
            return {"status": "no_data", "as_of": now_iso}

        entity_data = {}
        for row in rows:
            sym = row[0]
            if sym in entity_data:
                continue
            entity_data[sym] = {
                "curve_slope": round(row[1], 6) if row[1] else 0.0,
                "structure": row[2] or "unknown",
                "roll_yield_7d_pct": round(row[3], 4) if row[3] else 0.0,
                "term_premium": round(row[4], 4) if row[4] else 0.0,
                "convexity": round(row[5], 4) if row[5] else 0.0,
                "snapshot_ts": row[6],
            }

        # 全局信号汇总
        contango_count = sum(1 for v in entity_data.values() if v["structure"] == "contango")
        backwardation_count = sum(1 for v in entity_data.values() if v["structure"] == "backwardation")
        avg_slope = statistics.mean([v["curve_slope"] for v in entity_data.values()]) if entity_data else 0

        # 异常检测：期限溢价超过阈值
        anomalies = []
        for sym, data in entity_data.items():
            if abs(data["term_premium"]) > 0.5:
                anomalies.append({
                    "symbol": sym,
                    "term_premium": data["term_premium"],
                    "severity": "high" if abs(data["term_premium"]) > 1.0 else "medium",
                })

        return {
            "status": "ready",
            "as_of": now_iso,
            "coverage": {
                "symbols_with_data": len(entity_data),
                "symbols_requested": len(symbols),
            },
            "market_structure": {
                "dominant_regime": "contango" if contango_count > backwardation_count
                    else "backwardation" if backwardation_count > contango_count else "mixed",
                "contango_assets": contango_count,
                "backwardation_assets": backwardation_count,
                "avg_curve_slope": round(avg_slope, 6),
            },
            "anomalies": anomalies,
            "entities": entity_data,
        }

    def build_scheduler(self, symbols: list[str] | None = None):
        from apscheduler.schedulers.blocking import BlockingScheduler
        scheduler = BlockingScheduler()
        scheduler.add_job(
            self.collect_once, "interval", minutes=60,
            kwargs={"symbols": symbols}, id="perpetual_basis_curve_collect",
        )
        return scheduler

    def build_async_scheduler(self, symbols: list[str] | None = None):
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        scheduler = AsyncIOScheduler()
        scheduler.add_job(
            self.collect_once, "interval", minutes=60,
            kwargs={"symbols": symbols}, id="perpetual_basis_curve_collect",
        )
        return scheduler

    def close(self):
        self.client.close()
