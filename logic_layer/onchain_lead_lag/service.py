"""链上领先-滞后服务：编排互相关、Granger 因果、预测力计算。"""

from __future__ import annotations

from datetime import datetime, timezone

from loguru import logger

from database.db_manager import DBManager
from logic_layer.onchain_lead_lag.calculator import OnchainLeadLagCalculator
from logic_layer.onchain_lead_lag.repository import OnchainLeadLagRepository


class OnchainLeadLagService:
    """链上领先-滞后编排服务。

    职责：
    - 从各链上数据表读取信号序列
    - 从 merged_klines 读取价格收益率
    - 调用 calculator 计算互相关、最优滞后、Granger 因果
    - 检测信号触发并生成告警
    - 通过 repository 落库
    """

    # 信号源映射：信号名 -> (表名, 值列名, 时间列名)
    SIGNAL_SOURCES: dict[str, dict] = {
        "whale_net_flow": {
            "table": "whale_moves",
            "value_col": "amount_usd",
            "time_col": "ts",
        },
        "exchange_inflow": {
            "table": "address_flows",
            "value_col": "net_flow",
            "time_col": "ts",
        },
        "gas_spike": {
            "table": "gas_spikes",
            "value_col": "gas_price",
            "time_col": "ts",
        },
        "funding_rate": {
            "table": "perp_dex_funding",
            "value_col": "funding_rate",
            "time_col": "ts",
        },
        "open_interest_change": {
            "table": "open_interest",
            "value_col": "oi_change",
            "time_col": "ts",
        },
    }

    SYMBOLS: list[str] = ["BTC", "ETH", "SOL"]

    def __init__(self, db: DBManager | None = None):
        if db is not None:
            self.db = db
        else:
            from database.router import DatabaseRouter
            self.db = DatabaseRouter().get_analytics_db()
        self.repository = OnchainLeadLagRepository(self.db)
        self.calculator = OnchainLeadLagCalculator()

    def init_storage(self):
        """创建链上领先-滞后分析所需的数据库表。"""
        self.repository.ensure_tables()

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()

    # ------------------------------------------------------------------
    # 数据读取
    # ------------------------------------------------------------------

    def _load_signal_series(
        self, signal_name: str, hours: int = 168
    ) -> list[float]:
        """从对应数据表加载信号时间序列。

        Parameters
        ----------
        signal_name : str
            信号名称（对应 SIGNAL_SOURCES 的 key）
        hours : int
            回溯窗口（小时数，默认 168 = 7 天）

        Returns
        -------
        list[float]
            信号值序列（时间正序）
        """
        source = self.SIGNAL_SOURCES.get(signal_name)
        if not source:
            logger.warning("未知信号源: {}", signal_name)
            return []

        table = source["table"]
        value_col = source["value_col"]
        time_col = source["time_col"]

        try:
            rows = self.db.fetch_all(
                f"""SELECT {value_col}
                   FROM {table}
                   ORDER BY {time_col} DESC
                   LIMIT ?""",
                (hours,),
            )
        except Exception as exc:
            logger.debug("加载信号 {} 失败: {}", signal_name, exc)
            return []

        if not rows:
            return []

        # 反转为时间正序
        values = [float(r[value_col]) for r in rows if r[value_col] is not None]
        values.reverse()
        return values

    def _load_price_returns(
        self, symbol: str, hours: int = 168
    ) -> list[float]:
        """从 merged_klines 加载价格收益率序列。

        Parameters
        ----------
        symbol : str
            交易对基础资产（BTC/ETH/SOL），自动拼接 /USDT
        hours : int
            回溯窗口（小时数）

        Returns
        -------
        list[float]
            小时收益率序列（时间正序）
        """
        pair = f"{symbol}/USDT"
        try:
            rows = self.db.fetch_all(
                """SELECT close
                   FROM merged_klines
                   WHERE timeframe = '1h' AND symbol = ?
                   ORDER BY open_time DESC
                   LIMIT ?""",
                (pair, hours),
            )
        except Exception as exc:
            logger.debug("加载 {} 价格失败: {}", pair, exc)
            return []

        if not rows or len(rows) < 2:
            return []

        prices = [float(r["close"]) for r in rows if r["close"] is not None]
        prices.reverse()

        # 转换为收益率
        returns = [
            (prices[i] / prices[i - 1]) - 1.0
            for i in range(1, len(prices))
            if prices[i - 1] > 0
        ]
        return returns

    # ------------------------------------------------------------------
    # 计算编排
    # ------------------------------------------------------------------

    def run_all(self) -> dict:
        """对每个信号源和交易对执行领先-滞后分析并落库。

        Returns
        -------
        dict
            包含 signals, relations, alerts 的分析结果
        """
        ts = self._utc_now_iso()
        signal_entries: list[dict] = []
        relation_entries: list[dict] = []
        alert_entries: list[dict] = []

        for signal_name in self.SIGNAL_SOURCES:
            signal_series = self._load_signal_series(signal_name)
            if len(signal_series) < 20:
                logger.debug("信号 {} 数据不足，跳过", signal_name)
                continue

            # 检测信号触发
            triggered = self.calculator.detect_signal_trigger(signal_series)

            for symbol in self.SYMBOLS:
                price_returns = self._load_price_returns(symbol)
                if len(price_returns) < 20:
                    logger.debug("{}/{} 价格数据不足，跳过", signal_name, symbol)
                    continue

                # 计算最优滞后
                optimal = self.calculator.find_optimal_lag(
                    signal_series, price_returns
                )
                lag = optimal["optimal_lag"]
                corr = optimal["correlation"]
                direction = optimal["direction"]

                # Granger 因果检验
                granger = self.calculator.compute_granger_causality(
                    signal_series, price_returns
                )

                # 预测力
                pred_power = self.calculator.compute_predictive_power(
                    signal_series, price_returns, lag if lag > 0 else 1
                )

                # 保存关系
                relation_entries.append({
                    "ts": ts,
                    "metric_name": signal_name,
                    "symbol": symbol,
                    "lead_lag_hours": lag,
                    "granger_f_stat": granger["f_stat"],
                    "predictive_power": pred_power,
                })

                # 如果信号触发且有显著领先关系，生成告警
                if triggered and lag > 0 and granger["significant"]:
                    expected_dir = "up" if direction == "positive" else "down"
                    alert_entries.append({
                        "ts": ts,
                        "signal_name": signal_name,
                        "symbol": symbol,
                        "current_value": signal_series[-1],
                        "threshold": 2.0,
                        "triggered_at": ts,
                        "expected_price_direction": expected_dir,
                    })

            # 汇总信号级别结果
            signal_entries.append({
                "ts": ts,
                "signal_name": signal_name,
                "lead_hours": lag if relation_entries else 0,
                "correlation": corr if relation_entries else 0.0,
                "p_value": granger["p_value_approx"] if relation_entries else 1.0,
                "direction": direction if relation_entries else "none",
                "last_triggered": ts if triggered else None,
            })

        # 落库
        if signal_entries:
            self.repository.save_lead_lag_signals(signal_entries)
        if relation_entries:
            self.repository.save_price_relations(relation_entries)
        if alert_entries:
            self.repository.save_alerts(alert_entries)

        logger.info(
            "链上领先-滞后分析完成: {} 信号, {} 关系, {} 告警",
            len(signal_entries), len(relation_entries), len(alert_entries),
        )

        return {
            "ts": ts,
            "signals": signal_entries,
            "relations": relation_entries,
            "alerts": alert_entries,
        }

    def load_latest_context_bundle(self) -> dict:
        """加载最新链上领先-滞后分析结果，供 AI 上下文消费。

        Returns
        -------
        dict
            包含最强领先信号、活跃告警、预测力排名的上下文包
        """
        signals = self.repository.load_latest_signals()
        relations = self.repository.load_latest_relations()
        alerts = self.repository.load_active_alerts()

        # 最强领先信号（正滞后、高相关）
        strong_leads = [
            s for s in signals
            if (s.get("lead_hours") or 0) > 0
            and abs(s.get("correlation") or 0) > 0.3
        ]

        # 预测力排名
        predictive_ranking = sorted(
            relations,
            key=lambda r: r.get("predictive_power") or 0,
            reverse=True,
        )[:10]

        return {
            "as_of": self._utc_now_iso(),
            "strongest_lead_signals": strong_leads,
            "active_alerts": alerts,
            "predictive_ranking": predictive_ranking,
            "total_signals_analyzed": len(signals),
            "total_relations": len(relations),
        }

    def close(self):
        """关闭数据库连接。"""
        self.db.close()
