"""清算级联预测服务：编排聚集区识别、级联概率、热力图计算。"""

from __future__ import annotations

from datetime import datetime, timezone

from loguru import logger
from config.symbols import TARGET_ASSET_CODES

from database.db_manager import DBManager
from logic_layer.liquidation_cascade.calculator import LiquidationCascadeCalculator
from logic_layer.liquidation_cascade.repository import LiquidationCascadeRepository


class LiquidationCascadeService:
    """清算级联预测编排服务。

    职责：
    - 从 exchange_data 读取持仓/OI 数据
    - 调用 calculator 计算清算聚集区、级联概率、热力图
    - 通过 repository 落库
    """

    SYMBOLS: list[str] = TARGET_ASSET_CODES

    def __init__(self, db: DBManager | None = None):
        if db is not None:
            self.db = db
        else:
            from database.router import DatabaseRouter
            self.db = DatabaseRouter().get_analytics_db()
        self.repository = LiquidationCascadeRepository(self.db)
        self.calculator = LiquidationCascadeCalculator()

    def init_storage(self):
        """创建清算级联分析所需的数据库表。"""
        self.repository.ensure_tables()

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()

    # ------------------------------------------------------------------
    # 数据读取
    # ------------------------------------------------------------------

    def _load_position_data(self, symbol: str) -> list[dict]:
        """从 exchange_data 表加载持仓数据。

        Parameters
        ----------
        symbol : str
            标的符号（如 BTC）

        Returns
        -------
        list[dict]
            仓位列表，包含 liquidation_price, size_usd, leverage, direction
        """
        # 尝试从 open_interest 和 funding_rates 推算仓位分布
        like_pattern = f"{symbol}%"
        rows = self.db.fetch_all(
            """SELECT symbol, open_interest_usd AS open_interest,
                      COALESCE(open_interest_usd / NULLIF(open_interest_contracts, 0), 0) AS price
               FROM open_interest_snapshots
               WHERE symbol LIKE ?
               ORDER BY timestamp DESC
               LIMIT 100""",
            (like_pattern,),
        )
        if not rows:
            logger.debug("未找到 {} 的持仓数据", symbol)
            return []

        # 基于 OI 数据模拟仓位分布
        positions: list[dict] = []
        for row in rows:
            oi = float(row["open_interest"]) if row["open_interest"] else 0
            price = float(row["price"]) if row["price"] else 0
            if oi <= 0 or price <= 0:
                continue

            # 模拟多头和空头仓位（假设均匀分布不同杠杆）
            for leverage in [5, 10, 20, 50, 100]:
                size_per = oi / 10.0  # 每个杠杆档位占 10%
                # 多头清算价 = 入场价 * (1 - 1/leverage)
                long_liq = price * (1.0 - 1.0 / leverage)
                positions.append({
                    "liquidation_price": long_liq,
                    "size_usd": size_per,
                    "leverage": leverage,
                    "direction": "long",
                })
                # 空头清算价 = 入场价 * (1 + 1/leverage)
                short_liq = price * (1.0 + 1.0 / leverage)
                positions.append({
                    "liquidation_price": short_liq,
                    "size_usd": size_per,
                    "leverage": leverage,
                    "direction": "short",
                })

        return positions

    def _get_current_price(self, symbol: str) -> float:
        """从 klines 获取最新价格。

        Parameters
        ----------
        symbol : str
            标的符号（如 BTC）

        Returns
        -------
        float
            最新收盘价，无数据时返回 0.0
        """
        like_pattern = f"{symbol}%"
        row = self.db.fetch_all(
            """SELECT close FROM klines
               WHERE symbol LIKE ?
               ORDER BY open_time DESC LIMIT 1""",
            (like_pattern,),
        )
        if row:
            return float(row[0]["close"])
        return 0.0

    def _get_daily_volume(self, symbol: str) -> float:
        """从 klines 获取 24h 成交量（USD）。"""
        like_pattern = f"{symbol}%"
        rows = self.db.fetch_all(
            """SELECT volume, close FROM klines
               WHERE symbol LIKE ?
               ORDER BY open_time DESC LIMIT 24""",
            (like_pattern,),
        )
        if not rows:
            return 0.0
        total = sum(
            float(r["volume"]) * float(r["close"])
            for r in rows
            if r["volume"] and r["close"]
        )
        return total

    def _get_open_interest_usd(self, symbol: str) -> float:
        """获取当前未平仓合约总量（USD）。"""
        like_pattern = f"{symbol}%"
        row = self.db.fetch_all(
            """SELECT open_interest_usd FROM open_interest_snapshots
               WHERE symbol LIKE ?
               ORDER BY timestamp DESC LIMIT 1""",
            (like_pattern,),
        )
        if row and row[0]["open_interest_usd"]:
            return float(row[0]["open_interest_usd"])
        return 0.0

    # ------------------------------------------------------------------
    # 计算编排
    # ------------------------------------------------------------------

    def run_all(self, symbols: list[str] | None = None) -> dict:
        """执行全部清算级联分析计算并落库。

        Parameters
        ----------
        symbols : list[str] | None
            目标标的列表，默认使用 SYMBOLS

        Returns
        -------
        dict
            包含 clusters, cascade_risk, heatmap 的结果
        """
        if symbols is None:
            symbols = self.SYMBOLS

        ts = self._utc_now_iso()
        all_clusters: list[dict] = []
        all_risks: list[dict] = []
        all_heatmap: list[dict] = []

        for symbol in symbols:
            logger.info("计算 {} 清算级联...", symbol)

            current_price = self._get_current_price(symbol)
            if current_price <= 0:
                logger.warning("{} 无法获取当前价格，跳过", symbol)
                continue

            positions = self._load_position_data(symbol)
            if not positions:
                logger.warning("{} 无持仓数据，跳过", symbol)
                continue

            daily_volume = self._get_daily_volume(symbol)
            oi_usd = self._get_open_interest_usd(symbol)

            # 1. 计算清算聚集区
            clusters = self.calculator.compute_liquidation_clusters(
                positions, current_price
            )
            for c in clusters:
                c["ts"] = ts
                c["symbol"] = symbol
            all_clusters.extend(clusters)

            # 2. 计算级联风险（按方向分别评估）
            for direction in ["long", "short"]:
                dir_clusters = [
                    c for c in clusters if c["direction"] == direction
                ]
                if not dir_clusters:
                    continue
                # 取最大的聚集区
                biggest = max(dir_clusters, key=lambda c: c["total_size_usd"])
                cluster_size = biggest["total_size_usd"]
                distance = biggest["distance_pct"]

                prob = self.calculator.compute_cascade_probability(
                    cluster_size,
                    daily_volume if daily_volume > 0 else 1.0,
                    distance,
                )
                severity = self.calculator.compute_cascade_severity(
                    prob, cluster_size,
                    oi_usd if oi_usd > 0 else 1.0,
                )
                # 估算级联总量
                estimated = self.calculator.estimate_cascade_chain(
                    dir_clusters, cluster_size * prob,
                )

                all_risks.append({
                    "ts": ts,
                    "symbol": symbol,
                    "cascade_probability": prob,
                    "estimated_liquidation_usd": round(estimated, 2),
                    "price_trigger": biggest["price_level"],
                    "direction": direction,
                    "severity": severity,
                })

            # 3. 计算热力图
            heatmap = self.calculator.compute_heatmap(
                positions, current_price
            )
            for h in heatmap:
                h["ts"] = ts
                h["symbol"] = symbol
            all_heatmap.extend(heatmap)

        # 落库
        if all_clusters:
            self.repository.save_clusters(all_clusters)
        if all_risks:
            self.repository.save_cascade_risk(all_risks)
        if all_heatmap:
            self.repository.save_heatmap(all_heatmap)

        logger.info(
            "清算级联分析完成: {} 个聚集区, {} 条风险, {} 条热力图",
            len(all_clusters), len(all_risks), len(all_heatmap),
        )
        return {
            "ts": ts,
            "clusters_count": len(all_clusters),
            "risks_count": len(all_risks),
            "heatmap_count": len(all_heatmap),
            "symbols_processed": len(symbols),
        }

    # ------------------------------------------------------------------
    # 上下文输出
    # ------------------------------------------------------------------

    def load_latest_context_bundle(self) -> dict:
        """加载最新清算级联分析结果，供 AI 上下文消费。

        Returns
        -------
        dict
            包含 top cascade risks, critical clusters, 市场杠杆评估
        """
        risks = self.repository.load_latest_cascade_risk()
        clusters = self.repository.load_latest_clusters()

        # 筛选关键聚集区（距离 < 3%）
        critical_clusters = [
            c for c in clusters if c.get("distance_pct", 100) < 3.0
        ]

        # 市场整体杠杆评估
        if clusters:
            avg_leverage = sum(
                c.get("leverage_avg", 0) for c in clusters
            ) / len(clusters)
            total_liq_usd = sum(
                c.get("total_size_usd", 0) for c in clusters
            )
        else:
            avg_leverage = 0.0
            total_liq_usd = 0.0

        # 风险等级统计
        severity_counts = {}
        for r in risks:
            sev = r.get("severity", "low")
            severity_counts[sev] = severity_counts.get(sev, 0) + 1

        return {
            "as_of": self._utc_now_iso(),
            "top_cascade_risks": risks[:10],
            "critical_clusters": critical_clusters[:20],
            "market_leverage_assessment": {
                "avg_leverage": round(avg_leverage, 2),
                "total_liquidation_exposure_usd": round(total_liq_usd, 2),
                "severity_distribution": severity_counts,
            },
            "risk_regime": self._classify_overall_risk(risks),
        }

    @staticmethod
    def _classify_overall_risk(risks: list[dict]) -> str:
        """根据级联风险评估判定整体风险等级。"""
        if not risks:
            return "low"
        critical_count = sum(
            1 for r in risks if r.get("severity") == "critical"
        )
        high_count = sum(
            1 for r in risks if r.get("severity") == "high"
        )
        if critical_count >= 2:
            return "critical"
        elif critical_count >= 1 or high_count >= 3:
            return "elevated"
        elif high_count >= 1:
            return "moderate"
        else:
            return "low"

    def close(self):
        """关闭数据库连接。"""
        self.db.close()
