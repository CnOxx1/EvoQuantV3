"""流量分解服务：编排 VPIN、流量分类、吸筹/派发检测计算。"""

from __future__ import annotations

from datetime import datetime, timezone

from config.symbols import TARGET_SYMBOLS
from database.db_manager import DBManager
from logic_layer.flow_decomposition.calculator import FlowDecompositionCalculator
from logic_layer.flow_decomposition.repository import FlowDecompositionRepository


class FlowDecompositionService:
    """流量分解编排服务。

    职责：
    - 从 orderflow / whale_flow_agg 表读取原始数据
    - 调用 calculator 计算 VPIN、流量分类、吸筹/派发
    - 通过 repository 落库
    """

    def __init__(self, db: DBManager | None = None):
        if db is not None:
            self.db = db
        else:
            from database.router import DatabaseRouter
            self.db = DatabaseRouter().get_analytics_db()
        self.repository = FlowDecompositionRepository(self.db)
        self.calculator = FlowDecompositionCalculator()

    def init_storage(self):
        """创建流量分解所需的数据库表。"""
        self.repository.ensure_tables()

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()

    # ------------------------------------------------------------------
    # 数据读取
    # ------------------------------------------------------------------

    def _load_orderflow(self, symbol: str) -> list[dict]:
        """从 orderflow 表加载交易数据。"""
        rows = self.db.fetch_all(
            """SELECT volume, side, price, ts
               FROM orderflow
               WHERE symbol = ?
               ORDER BY ts DESC LIMIT 500""",
            (symbol,),
        )
        return [dict(r) for r in rows]

    def _load_whale_flows(self, symbol: str) -> list[dict]:
        """从 whale_flow_agg 表加载鲸鱼流量数据。"""
        rows = self.db.fetch_all(
            """SELECT net_flow, direction, ts
               FROM whale_flow_agg
               WHERE symbol = ?
               ORDER BY ts DESC LIMIT 100""",
            (symbol,),
        )
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # 计算编排
    # ------------------------------------------------------------------

    def compute_decomposition(self, symbol: str) -> dict:
        """计算单个 symbol 的流量分解。"""
        ts = self._utc_now_iso()
        trades = self._load_orderflow(symbol)
        whale_flows = self._load_whale_flows(symbol)

        # 计算 VPIN
        vpin = self.calculator.compute_vpin(trades, bucket_size=50)

        # 流量分类
        flow_class = self.calculator.classify_flow(trades)

        # 吸筹/派发检测
        net_flows = [float(w.get("net_flow", 0)) for w in whale_flows]
        # CVD 趋势：简单线性斜率
        cvd_trend = 0.0
        if len(net_flows) >= 2:
            cumulative = []
            running = 0.0
            for nf in reversed(net_flows):
                running += nf
                cumulative.append(running)
            if len(cumulative) >= 2:
                cvd_trend = cumulative[-1] - cumulative[0]

        phase = self.calculator.detect_accumulation_distribution(
            net_flows, cvd_trend
        )

        # VPIN 百分位
        vpin_history_rows = self.repository.load_vpin_history(symbol, limit=50)
        history_values = [r["vpin_value"] for r in vpin_history_rows if r.get("vpin_value") is not None]
        vpin_percentile = self.calculator.compute_vpin_percentile(vpin, history_values)

        # 告警级别
        if vpin_percentile >= 90:
            alert_level = "critical"
        elif vpin_percentile >= 75:
            alert_level = "warning"
        else:
            alert_level = "normal"

        # 组装结果
        entry = {
            "ts": ts,
            "symbol": symbol,
            "vpin": vpin,
            "informed_flow_ratio": flow_class["informed_flow_ratio"],
            "retail_flow_ratio": flow_class["retail_flow_ratio"],
            "smart_money_direction": flow_class["smart_money_direction"],
            "accumulation_phase": phase["accumulation_phase"],
            "distribution_phase": phase["distribution_phase"],
        }

        # 落库
        self.repository.save_decomposition([entry])
        self.repository.save_vpin([{
            "ts": ts,
            "symbol": symbol,
            "vpin_value": vpin,
            "vpin_percentile": vpin_percentile,
            "alert_level": alert_level,
        }])

        return entry

    def run_all(self, symbols: list[str] | None = None) -> dict:
        """执行全部 symbol 的流量分解计算并落库。"""
        target = symbols or TARGET_SYMBOLS
        results: dict = {}
        for symbol in target:
            try:
                results[symbol] = self.compute_decomposition(symbol)
            except Exception:
                results[symbol] = None
        return results

    def load_latest_context_bundle(self) -> dict:
        """加载最新流量分解结果，供 AI 上下文消费。"""
        bundle: dict = {"as_of": self._utc_now_iso(), "decompositions": {}}
        for symbol in TARGET_SYMBOLS:
            latest = self.repository.load_latest_decomposition(symbol)
            if latest:
                bundle["decompositions"][symbol] = latest
        return bundle

    def close(self):
        self.db.close()