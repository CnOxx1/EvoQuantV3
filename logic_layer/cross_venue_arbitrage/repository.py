"""跨场所套利数据库读写。"""

from __future__ import annotations

from database.db_manager import DBManager


class CrossVenueArbRepository:
    """跨场所套利分析结果的读取与落库。"""

    def __init__(self, db: DBManager):
        self.db = db

    def ensure_tables(self):
        """创建跨场所套利分析所需的数据库表。"""
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS arb_opportunities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                symbol TEXT NOT NULL,
                venue_buy TEXT NOT NULL,
                venue_sell TEXT NOT NULL,
                price_buy REAL,
                price_sell REAL,
                spread_bps REAL,
                estimated_profit_usd REAL,
                latency_ms INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(ts, symbol, venue_buy, venue_sell)
            )
        """)
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS arb_persistence (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                symbol TEXT NOT NULL,
                venue_pair TEXT NOT NULL,
                avg_spread_bps REAL,
                duration_seconds INTEGER,
                frequency_per_hour REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(ts, symbol, venue_pair)
            )
        """)
        self._create_venue_spreads_table()
        self.db.conn.commit()

    def _create_venue_spreads_table(self):
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS venue_spreads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                symbol TEXT NOT NULL,
                venue_a TEXT NOT NULL,
                venue_b TEXT NOT NULL,
                mid_spread_bps REAL,
                bid_ask_cross INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(ts, symbol, venue_a, venue_b)
            )
        """)

    # ------------------------------------------------------------------
    # 套利机会
    # ------------------------------------------------------------------

    def save_opportunities(self, entries: list[dict]):
        """批量保存套利机会。"""
        for e in entries:
            self.db.conn.execute(
                """INSERT OR REPLACE INTO arb_opportunities
                   (ts, symbol, venue_buy, venue_sell, price_buy,
                    price_sell, spread_bps, estimated_profit_usd,
                    latency_ms)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    e["ts"], e["symbol"],
                    e["venue_buy"], e["venue_sell"],
                    e.get("price_buy"), e.get("price_sell"),
                    e.get("spread_bps"),
                    e.get("estimated_profit_usd"),
                    e.get("latency_ms"),
                ),
            )
        self.db.conn.commit()

    # ------------------------------------------------------------------
    # 套利持续性
    # ------------------------------------------------------------------

    def save_persistence(self, entries: list[dict]):
        """批量保存套利持续性指标。"""
        for e in entries:
            self.db.conn.execute(
                """INSERT OR REPLACE INTO arb_persistence
                   (ts, symbol, venue_pair, avg_spread_bps,
                    duration_seconds, frequency_per_hour)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    e["ts"], e["symbol"], e["venue_pair"],
                    e.get("avg_spread_bps"),
                    e.get("duration_seconds"),
                    e.get("frequency_per_hour"),
                ),
            )
        self.db.conn.commit()

    # ------------------------------------------------------------------
    # 场所间价差
    # ------------------------------------------------------------------

    def save_spreads(self, entries: list[dict]):
        """批量保存场所间价差。"""
        for e in entries:
            self.db.conn.execute(
                """INSERT OR REPLACE INTO venue_spreads
                   (ts, symbol, venue_a, venue_b,
                    mid_spread_bps, bid_ask_cross)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    e["ts"], e["symbol"],
                    e["venue_a"], e["venue_b"],
                    e.get("mid_spread_bps"),
                    int(e.get("bid_ask_cross", 0)),
                ),
            )
        self.db.conn.commit()

    # ------------------------------------------------------------------
    # 数据加载
    # ------------------------------------------------------------------

    def load_latest_opportunities(
        self, symbol: str | None = None
    ) -> list[dict]:
        """加载最新一批套利机会。"""
        if symbol:
            rows = self.db.fetch_all(
                """SELECT ts, symbol, venue_buy, venue_sell,
                          price_buy, price_sell, spread_bps,
                          estimated_profit_usd, latency_ms
                   FROM arb_opportunities
                   WHERE ts = (
                       SELECT MAX(ts) FROM arb_opportunities
                   ) AND symbol = ?
                   ORDER BY spread_bps DESC""",
                (symbol,),
            )
        else:
            rows = self.db.fetch_all(
                """SELECT ts, symbol, venue_buy, venue_sell,
                          price_buy, price_sell, spread_bps,
                          estimated_profit_usd, latency_ms
                   FROM arb_opportunities
                   WHERE ts = (
                       SELECT MAX(ts) FROM arb_opportunities
                   )
                   ORDER BY spread_bps DESC""",
                (),
            )
        return [dict(r) for r in rows] if rows else []

    def load_latest_persistence(self) -> list[dict]:
        """加载最新一批套利持续性指标。"""
        rows = self.db.fetch_all(
            """SELECT ts, symbol, venue_pair, avg_spread_bps,
                      duration_seconds, frequency_per_hour
               FROM arb_persistence
               WHERE ts = (
                   SELECT MAX(ts) FROM arb_persistence
               )
               ORDER BY avg_spread_bps DESC""",
            (),
        )
        return [dict(r) for r in rows] if rows else []

    def load_latest_spreads(self) -> list[dict]:
        """加载最新一批场所间价差。"""
        rows = self.db.fetch_all(
            """SELECT ts, symbol, venue_a, venue_b,
                      mid_spread_bps, bid_ask_cross
               FROM venue_spreads
               WHERE ts = (
                   SELECT MAX(ts) FROM venue_spreads
               )
               ORDER BY mid_spread_bps DESC""",
            (),
        )
        return [dict(r) for r in rows] if rows else []
