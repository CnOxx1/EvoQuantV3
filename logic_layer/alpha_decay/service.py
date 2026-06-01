"""信号衰减与拥挤度分析服务：编排衰减计算与拥挤度评估。"""

from __future__ import annotations

from datetime import datetime, timezone

from database.db_manager import DBManager
from logic_layer.alpha_decay.calculator import AlphaDecayCalculator
from logic_layer.alpha_decay.repository import AlphaDecayRepository


class AlphaDecayService:
    """信号衰减与拥挤度编排服务。

    职责：
    - 从各逻辑层模块加载最新信号
    - 调用 calculator 计算半衰期与拥挤度
    - 通过 repository 落库
    """

    def __init__(self, db: DBManager | None = None):
        if db is not None:
            self.db = db
        else:
            from database.router import DatabaseRouter
            self.db = DatabaseRouter().get_analytics_db()
        self.repository = AlphaDecayRepository(self.db)
        self.calculator = AlphaDecayCalculator()

    def init_storage(self):
        """创建信号衰减与拥挤度所需的数据库表。"""
        self.repository.ensure_tables()

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()

    # ------------------------------------------------------------------
    # 数据读取
    # ------------------------------------------------------------------

    def _load_all_signals(self) -> list[dict]:
        """从各逻辑层模块加载最新信号数据。"""
        signals = []
        # 尝试从各分析模块的结果表中获取信号
        tables_to_query = [
            ("momentum_signals", "momentum"),
            ("volatility_signals", "volatility"),
            ("orderflow_signals", "orderflow"),
            ("microstructure_signals", "microstructure"),
            ("sentiment_signals", "sentiment"),
        ]
        for table_name, module_source in tables_to_query:
            try:
                rows = self.db.fetch_all(
                    f"""SELECT * FROM {table_name}
                        ORDER BY ts DESC LIMIT 50""",
                    (),
                )
                for row in rows:
                    r = dict(row)
                    r["module_source"] = module_source
                    signals.append(r)
            except Exception:
                # 表可能不存在，跳过
                continue
        return signals

    # ------------------------------------------------------------------
    # 计算编排
    # ------------------------------------------------------------------

    def compute_decay(self) -> list[dict]:
        """计算各信号的半衰期并落库。"""
        signals = self._load_all_signals()
        if not signals:
            return []

        ts = self._utc_now_iso()
        # 按 signal_name 分组
        grouped: dict[str, list[dict]] = {}
        for s in signals:
            name = s.get("signal_name", s.get("name", "unknown"))
            grouped.setdefault(name, []).append(s)

        entries = []
        for signal_name, group in grouped.items():
            # 提取信号强度序列
            values = [
                float(g.get("strength", g.get("value", 0)))
                for g in group
                if g.get("strength") is not None or g.get("value") is not None
            ]
            if len(values) < 4:
                continue

            half_life = self.calculator.compute_half_life(values)
            autocorrelation = self.calculator.compute_autocorrelation(values)
            current_strength = values[-1] if values else 0.0
            decay_rate = (1.0 / half_life) if half_life > 0 else 0.0

            entries.append({
                "ts": ts,
                "signal_name": signal_name,
                "module_source": group[0].get("module_source", ""),
                "half_life_hours": round(half_life, 2),
                "autocorrelation": round(autocorrelation, 4),
                "current_strength": round(current_strength, 4),
                "decay_rate": round(decay_rate, 4),
            })

        if entries:
            self.repository.save_signal_decay(entries)
        return entries

    def compute_crowding(self) -> dict:
        """计算信号拥挤度并落库。"""
        signals = self._load_all_signals()
        if not signals:
            return {}

        ts = self._utc_now_iso()

        # 构建信号方向列表
        signal_directions = []
        for s in signals:
            direction = s.get("direction", 0)
            if direction == 0:
                # 从 strength 推断方向
                strength = float(s.get("strength", s.get("value", 0)) or 0)
                direction = 1 if strength > 0 else -1 if strength < 0 else 0
            signal_directions.append({
                "signal_name": s.get("signal_name", s.get("name", "unknown")),
                "direction": direction,
                "strength": float(s.get("strength", s.get("value", 0)) or 0),
            })

        crowding = self.calculator.compute_crowding_score(signal_directions)

        # 计算信号惊奇度（使用最新信号的强度 vs 历史）
        strengths = [
            float(s.get("strength", s.get("value", 0)) or 0)
            for s in signals
        ]
        current = strengths[0] if strengths else 0.0
        history = strengths[1:] if len(strengths) > 1 else []
        surprise = self.calculator.compute_signal_surprise(current, history)

        entry = {
            "ts": ts,
            "crowding_score": crowding["crowding_score"],
            "agreeing_signals": crowding["agreeing_signals"],
            "disagreeing_signals": crowding["disagreeing_signals"],
            "contrarian_signal": crowding["contrarian_signal"],
            "signal_surprise_index": surprise,
        }

        self.repository.save_crowding_index(entry)
        return entry

    # ------------------------------------------------------------------
    # 主编排
    # ------------------------------------------------------------------

    def run_all(self) -> dict:
        """执行全部信号衰减与拥挤度计算并落库。"""
        results: dict = {}
        results["decay"] = self.compute_decay()
        results["crowding"] = self.compute_crowding()
        return results

    def load_latest_context_bundle(self) -> dict:
        """加载最新信号衰减与拥挤度结果，供 AI 上下文消费。"""
        decay = self.repository.load_latest_decay()
        crowding = self.repository.load_latest_crowding()
        return {
            "as_of": self._utc_now_iso(),
            "signal_decay": decay,
            "crowding_index": crowding,
        }

    def close(self):
        self.db.close()
