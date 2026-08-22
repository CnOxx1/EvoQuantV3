from __future__ import annotations

from datetime import datetime, timezone

from loguru import logger

from data_layer.exchange_reserve_data.client import ExchangeReserveDataClient


class ExchangeReserveDataService:
    """仅记录可验证的官方交易所储备证明快照。"""

    def __init__(self, client=None, db=None):
        if db is not None:
            self.db = db
        else:
            from database.router import DatabaseRouter, Domain
            self.db = DatabaseRouter().get_manager(Domain.MARKET_DATA)
        self.client = client or ExchangeReserveDataClient()

    def init_storage(self):
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS exchange_reserves (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                exchange TEXT NOT NULL,
                asset TEXT NOT NULL,
                reserve_balance REAL DEFAULT 0,
                report_at TEXT DEFAULT '',
                source_url TEXT DEFAULT '',
                source_kind TEXT DEFAULT '',
                collected_at TEXT NOT NULL,
                UNIQUE(exchange, asset, report_at)
            )
        """)
        existing = {row[1] for row in self.db.conn.execute("PRAGMA table_info(exchange_reserves)")}
        for column in ("report_at", "source_url", "source_kind"):
            if column not in existing:
                self.db.conn.execute(f"ALTER TABLE exchange_reserves ADD COLUMN {column} TEXT DEFAULT ''")
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS exchange_reserve_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                exchange TEXT NOT NULL,
                report_at TEXT NOT NULL,
                source_url TEXT NOT NULL,
                source_kind TEXT NOT NULL,
                asset_count INTEGER NOT NULL,
                collected_at TEXT NOT NULL,
                UNIQUE(exchange, report_at)
            )
        """)
        self.db.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_exchange_reserves_lookup
            ON exchange_reserves(exchange, asset, report_at DESC)
        """)
        self.db.conn.commit()
        logger.info("exchange_reserve_data 存储初始化完成")

    def bootstrap(self):
        self.collect_once()

    def collect_once(self):
        """采集最新 OKX 官方储备证明快照。"""
        collected_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        report = self.client.fetch_okx_reserves()
        if not report:
            logger.warning("OKX 官方 PoR 报告未返回可验证资产余额")
            return
        assets = report["assets"]
        self.db.conn.execute("""
            INSERT INTO exchange_reserve_reports
            (exchange, report_at, source_url, source_kind, asset_count, collected_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(exchange, report_at) DO UPDATE SET
                source_url=excluded.source_url,
                source_kind=excluded.source_kind,
                asset_count=excluded.asset_count,
                collected_at=excluded.collected_at
        """, (
            report["exchange"], report["report_at"], report["archive_url"],
            report["source_kind"], len(assets), collected_at,
        ))
        for item in assets:
            self.db.conn.execute("""
                DELETE FROM exchange_reserves
                WHERE exchange = ? AND asset = ? AND report_at = ?
            """, (report["exchange"], item["asset"], report["report_at"]))
            self.db.conn.execute("""
                INSERT INTO exchange_reserves
                (exchange, asset, reserve_balance, report_at, source_url, source_kind, collected_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                report["exchange"], item["asset"], item["reserve_balance"],
                report["report_at"], report["archive_url"], report["source_kind"], collected_at,
            ))
        self.db.conn.commit()
        logger.info("OKX 官方 PoR 采集完成，写入 {} 种资产", len(assets))

    def load_latest_context_bundle(self) -> dict:
        row = self.db.conn.execute("""
            SELECT exchange, report_at, source_url, asset_count, collected_at
            FROM exchange_reserve_reports
            ORDER BY report_at DESC LIMIT 1
        """).fetchone()
        if not row:
            return {"status": "no_data"}
        exchange, report_at, source_url, asset_count, collected_at = row
        assets = self.db.conn.execute("""
            SELECT asset, reserve_balance FROM exchange_reserves
            WHERE exchange = ? AND report_at = ? ORDER BY reserve_balance DESC LIMIT 20
        """, (exchange, report_at)).fetchall()
        return {
            "status": "ready",
            "as_of": report_at,
            "exchange": exchange,
            "asset_count": asset_count,
            "source_url": source_url,
            "assets": [{"asset": asset, "reserve_balance": balance} for asset, balance in assets],
            "interpretation": "官方 PoR 报告快照，不表示实时交易所净流量或全市场储备。",
            "collected_at": collected_at,
        }

    def close(self):
        self.client.close()
