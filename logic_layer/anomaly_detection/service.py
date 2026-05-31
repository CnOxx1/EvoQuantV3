"""anomaly_detection 服务层。"""

from datetime import datetime, timezone

from loguru import logger

from logic_layer.anomaly_detection.detector import AnomalyDetector
from logic_layer.anomaly_detection.repository import AnomalyDetectionRepository


TARGET_SYMBOLS = ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "DOGE", "AVAX", "DOT", "LINK", "ARB", "OP"]


class AnomalyDetectionService:
    """异常检测服务。"""

    def __init__(self, db=None):
        if db is not None:
            self.db = db
        else:
            from database.router import DatabaseRouter
            self.db = DatabaseRouter().get_analytics_db()
        self.repository = AnomalyDetectionRepository(self.db)
        self.detector = AnomalyDetector()

    def init_storage(self):
        """初始化存储。"""
        self.repository.ensure_tables()
        logger.info("anomaly_detection 存储初始化完成")

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

    def run_detection(self, symbols: list[str] | None = None, save: bool = True) -> dict:
        """执行异常检测。"""
        symbols = symbols or TARGET_SYMBOLS
        now_iso = self._utc_now_iso()
        all_anomalies = {}

        for symbol in symbols:
            anomalies = self._detect_for_symbol(symbol)
            if anomalies:
                all_anomalies[symbol] = anomalies
                if save:
                    for a in anomalies:
                        self.repository.save_anomaly(symbol, a, now_iso)

        total = sum(len(v) for v in all_anomalies.values())
        critical = sum(1 for v in all_anomalies.values() for a in v if a["severity"] == "critical")

        return {
            "status": "ok",
            "as_of": now_iso,
            "total_anomalies": total,
            "critical_count": critical,
            "affected_symbols": list(all_anomalies.keys()),
            "details": all_anomalies,
        }

    def _detect_for_symbol(self, symbol: str) -> list[dict]:
        """对单个标的执行全维度异常检测。"""
        anomalies = []
        try:
            from database.router import DatabaseRouter, Domain
            market_db = DatabaseRouter().get_manager(Domain.MARKET_DATA)

            # 获取价格数据
            cursor = market_db.conn.execute("""
                SELECT close, volume FROM merged_klines
                WHERE entity_key = ? ORDER BY open_time DESC LIMIT 100
            """, (symbol,))
            rows = cursor.fetchall()
            if len(rows) < 20:
                return []

            closes = [r[0] for r in reversed(rows)]
            volumes = [r[1] for r in reversed(rows)]

            # 收益率序列
            returns = [(closes[i] - closes[i-1]) / closes[i-1]
                       for i in range(1, len(closes))]

            # 价格异常检测
            anomalies.extend(self.detector.detect_price_anomaly(returns))

            # 成交量异常检测
            anomalies.extend(self.detector.detect_volume_anomaly(volumes))

            # 资金费率异常检测
            cursor = market_db.conn.execute("""
                SELECT funding_rate FROM latest_funding_rates
                WHERE entity_key = ? ORDER BY collected_at DESC LIMIT 30
            """, (symbol,))
            funding_rows = cursor.fetchall()
            if len(funding_rows) >= 10:
                funding_rates = [r[0] for r in reversed(funding_rows)]
                anomalies.extend(self.detector.detect_funding_anomaly(funding_rates))

        except Exception as e:
            logger.debug(f"异常检测失败 [{symbol}]: {e}")

        return anomalies

    def load_latest_context_bundle(self, symbols: list[str] | None = None, hours: int = 24) -> dict:
        """输出 AI 可读的异常检测上下文 bundle。"""
        symbols = symbols or TARGET_SYMBOLS
        now_iso = self._utc_now_iso()

        recent = self.repository.fetch_recent_anomalies(hours=hours, limit=100)
        counts = self.repository.fetch_anomaly_counts(hours=hours)

        if not recent:
            return {"status": "no_data", "as_of": now_iso}

        # 过滤目标 symbols
        filtered = [r for r in recent if r["entity_key"] in symbols]
        filtered_counts = {k: v for k, v in counts.items() if k in symbols}

        # 全局风险评估
        total_critical = sum(v.get("critical", 0) for v in filtered_counts.values())
        total_warning = sum(v.get("warning", 0) for v in filtered_counts.values())

        if total_critical >= 5:
            market_risk = "high"
        elif total_critical >= 2 or total_warning >= 10:
            market_risk = "elevated"
        else:
            market_risk = "normal"

        # 按 entity 汇总
        entity_summaries = {}
        for entity, cnts in filtered_counts.items():
            total = cnts.get("critical", 0) + cnts.get("warning", 0) + cnts.get("info", 0)
            entity_summaries[entity] = {
                "total_anomalies": total,
                "critical": cnts.get("critical", 0),
                "warning": cnts.get("warning", 0),
                "risk_level": "high" if cnts.get("critical", 0) >= 2 else
                             "elevated" if cnts.get("critical", 0) >= 1 else "normal",
            }

        return {
            "status": "ready",
            "as_of": now_iso,
            "window": f"{hours}h",
            "market_risk_level": market_risk,
            "summary": {
                "total_anomalies": len(filtered),
                "critical_count": total_critical,
                "warning_count": total_warning,
                "affected_assets": len(filtered_counts),
            },
            "entity_summaries": entity_summaries,
            "recent_critical": [r for r in filtered if r["severity"] == "critical"][:10],
            "coverage": {
                "symbols_checked": len(symbols),
                "symbols_with_anomalies": len(filtered_counts),
            },
        }

    def close(self):
        pass
