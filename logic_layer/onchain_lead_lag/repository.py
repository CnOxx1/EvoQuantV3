"""链上领先-滞后分析数据库读写。"""

from __future__ import annotations

from database.db_manager import DBManager

_SQL_LEAD_LAG_SIGNALS = """
CREATE TABLE IF NOT EXISTS lead_lag_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    signal_name TEXT NOT NULL,
    lead_hours INTEGER,
    correlation REAL,
    p_value REAL,
    direction TEXT,
    last_triggered TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(ts, signal_name)
)"""

_SQL_ONCHAIN_PRICE_RELATIONS = """
CREATE TABLE IF NOT EXISTS onchain_price_relations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    symbol TEXT NOT NULL,
    lead_lag_hours INTEGER,
    granger_f_stat REAL,
    predictive_power REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(ts, metric_name, symbol)
)"""

_SQL_SIGNAL_ALERTS = """
CREATE TABLE IF NOT EXISTS signal_alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    signal_name TEXT NOT NULL,
    symbol TEXT NOT NULL,
    current_value REAL,
    threshold REAL,
    triggered_at TEXT,
    expected_price_direction TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(ts, signal_name, symbol)
)"""


class OnchainLeadLagRepository:
    """链上领先-滞后分析结果的读取与落库。"""

    def __init__(self, db: DBManager):
        self.db = db

    def ensure_tables(self):
        """创建链上领先-滞后分析所需的数据库表。"""
        self.db.conn.execute(_SQL_LEAD_LAG_SIGNALS)
        self.db.conn.execute(_SQL_ONCHAIN_PRICE_RELATIONS)
        self.db.conn.execute(_SQL_SIGNAL_ALERTS)
        self.db.conn.commit()

    # ------------------------------------------------------------------
    # 写入
    # ------------------------------------------------------------------

    def save_lead_lag_signals(self, entries: list[dict]):
        """批量保存领先-滞后信号。"""
        for e in entries:
            self.db.conn.execute(
                """INSERT OR REPLACE INTO lead_lag_signals
                   (ts, signal_name, lead_hours, correlation,
                    p_value, direction, last_triggered)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    e["ts"], e["signal_name"],
                    e.get("lead_hours"), e.get("correlation"),
                    e.get("p_value"), e.get("direction"),
                    e.get("last_triggered"),
                ),
            )
        self.db.conn.commit()

    def save_price_relations(self, entries: list[dict]):
        """批量保存链上指标与价格的领先-滞后关系。"""
        for e in entries:
            self.db.conn.execute(
                """INSERT OR REPLACE INTO onchain_price_relations
                   (ts, metric_name, symbol, lead_lag_hours,
                    granger_f_stat, predictive_power)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    e["ts"], e["metric_name"], e["symbol"],
                    e.get("lead_lag_hours"), e.get("granger_f_stat"),
                    e.get("predictive_power"),
                ),
            )
        self.db.conn.commit()

    def save_alerts(self, entries: list[dict]):
        """批量保存信号触发告警。"""
        for e in entries:
            self.db.conn.execute(
                """INSERT OR REPLACE INTO signal_alerts
                   (ts, signal_name, symbol, current_value,
                    threshold, triggered_at, expected_price_direction)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    e["ts"], e["signal_name"], e["symbol"],
                    e.get("current_value"), e.get("threshold"),
                    e.get("triggered_at"),
                    e.get("expected_price_direction"),
                ),
            )
        self.db.conn.commit()

    # ------------------------------------------------------------------
    # 读取
    # ------------------------------------------------------------------

    def load_latest_signals(self) -> list[dict]:
        """加载最新一批领先-滞后信号。"""
        rows = self.db.fetch_all(
            """SELECT ts, signal_name, lead_hours, correlation,
                      p_value, direction, last_triggered
               FROM lead_lag_signals
               WHERE ts = (SELECT MAX(ts) FROM lead_lag_signals)
               ORDER BY ABS(correlation) DESC""",
            (),
        )
        return [dict(r) for r in rows] if rows else []

    def load_latest_relations(self, symbol: str | None = None) -> list[dict]:
        """加载最新一批链上-价格关系。"""
        if symbol:
            rows = self.db.fetch_all(
                """SELECT ts, metric_name, symbol, lead_lag_hours,
                          granger_f_stat, predictive_power
                   FROM onchain_price_relations
                   WHERE ts = (
                       SELECT MAX(ts) FROM onchain_price_relations
                   ) AND symbol = ?
                   ORDER BY predictive_power DESC""",
                (symbol,),
            )
        else:
            rows = self.db.fetch_all(
                """SELECT ts, metric_name, symbol, lead_lag_hours,
                          granger_f_stat, predictive_power
                   FROM onchain_price_relations
                   WHERE ts = (
                       SELECT MAX(ts) FROM onchain_price_relations
                   )
                   ORDER BY predictive_power DESC""",
                (),
            )
        return [dict(r) for r in rows] if rows else []

    def load_active_alerts(self) -> list[dict]:
        """加载最近 24 小时内的活跃告警。"""
        rows = self.db.fetch_all(
            """SELECT ts, signal_name, symbol, current_value,
                      threshold, triggered_at, expected_price_direction
               FROM signal_alerts
               WHERE ts = (SELECT MAX(ts) FROM signal_alerts)
               ORDER BY current_value DESC""",
            (),
        )
        return [dict(r) for r in rows] if rows else []
