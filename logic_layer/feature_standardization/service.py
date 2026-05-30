"""特征标准化编排服务。"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from config.symbols import SECTOR_DEFINITIONS, get_symbol_sector, get_symbol_tier
from database.db_manager import DBManager
from logic_layer.feature_standardization.calculator import FeatureStandardizationCalculator
from logic_layer.feature_standardization.registry import (
    COMPOSITE_DEFINITIONS,
    FEATURE_REGISTRY,
    MIN_BARS_7D,
    MIN_BARS_30D,
)
from logic_layer.feature_standardization.repository import FeatureStandardizationRepository

logger = logging.getLogger(__name__)


class FeatureStandardizationService:
    """特征标准化编排入口。"""

    def __init__(self, db: DBManager | None = None):
        if db is not None:
            self.db = db
        else:
            from database.router import DatabaseRouter
            self.db = DatabaseRouter().get_analytics_db()
        self.repository = FeatureStandardizationRepository(self.db)
        self.calculator = FeatureStandardizationCalculator()

    def init_storage(self):
        self.repository.ensure_tables()

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

    def run_standardization(self, timeframe: str = "1h", save: bool = True) -> dict:
        """主编排：加载 → 计算 → 持久化 → 返回摘要。"""
        snapshot_time = self._utc_now_iso()

        # 1. 加载数据
        df = self._load_indicators(timeframe)
        if df.empty:
            return {"status": "no_data", "snapshot_time": snapshot_time}

        symbols = sorted(df["symbol"].unique())
        n_symbols = len(symbols)

        # 2. 逐特征逐资产计算滚动标准化
        detail_rows: list[dict] = []
        latest_zscores: dict[str, dict[str, float | None]] = {}
        latest_pcts: dict[str, dict[str, float | None]] = {}

        for spec in FEATURE_REGISTRY:
            latest_zscores[spec.name] = {}
            latest_pcts[spec.name] = {}

            if spec.source_column not in df.columns:
                for symbol in symbols:
                    latest_zscores[spec.name][symbol] = None
                    latest_pcts[spec.name][symbol] = None
                continue

            for symbol in symbols:
                asset_df = df[df["symbol"] == symbol].sort_values("open_time")
                series = pd.to_numeric(asset_df[spec.source_column], errors="coerce")
                available = int(series.notna().sum())

                if available < 2:
                    latest_zscores[spec.name][symbol] = None
                    latest_pcts[spec.name][symbol] = None
                    continue

                z7 = self.calculator.rolling_zscore(series, MIN_BARS_7D)
                z30 = self.calculator.rolling_zscore(series, MIN_BARS_30D)
                pct30 = self.calculator.rolling_percentile_rank(series, MIN_BARS_30D)

                raw_val = series.iloc[-1] if len(series) > 0 else None
                z7_val = z7.iloc[-1] if len(z7) > 0 else None
                z30_val = z30.iloc[-1] if len(z30) > 0 else None
                pct_val = pct30.iloc[-1] if len(pct30) > 0 else None

                # NaN → None
                raw_val = None if pd.isna(raw_val) else float(raw_val)
                z7_val = None if pd.isna(z7_val) else float(z7_val)
                z30_val = None if pd.isna(z30_val) else float(z30_val)
                pct_val = None if pd.isna(pct_val) else float(pct_val)

                latest_zscores[spec.name][symbol] = z30_val
                latest_pcts[spec.name][symbol] = pct_val

                confidence = self.calculator.compute_confidence(available, MIN_BARS_30D)
                regime = self.calculator.classify_regime(z30_val)

                detail_rows.append({
                    "snapshot_time": snapshot_time,
                    "symbol": symbol,
                    "feature_name": spec.name,
                    "raw_value": raw_val,
                    "zscore_7d": z7_val,
                    "zscore_30d": z30_val,
                    "percentile_30d": pct_val,
                    "cross_asset_rank": None,
                    "cross_asset_rank_total": n_symbols,
                    "regime_label": regime,
                    "confidence": confidence,
                })

        # 3. 跨资产排名
        for spec in FEATURE_REGISTRY:
            if "cross_rank" not in spec.methods:
                continue
            ranks = self.calculator.cross_asset_rank(
                latest_zscores.get(spec.name, {}), ascending=spec.invert
            )
            for row in detail_rows:
                if row["feature_name"] == spec.name:
                    row["cross_asset_rank"] = ranks.get(row["symbol"])

        # 4. 复合信号
        composite_rows = self._compute_composites(
            latest_zscores, latest_pcts, symbols, n_symbols, snapshot_time
        )

        # 5. 构建 AI bundle
        bundle = self._build_ai_bundle(
            detail_rows, composite_rows, symbols, snapshot_time
        )

        # 6. 持久化
        if save:
            self.repository.save_details(detail_rows)
            self.repository.save_composites(composite_rows)
            self.repository.save_snapshot_bundle(
                snapshot_time, n_symbols, len(FEATURE_REGISTRY),
                len(COMPOSITE_DEFINITIONS), json.dumps(bundle, ensure_ascii=False),
            )

        return {
            "status": "ok",
            "snapshot_time": snapshot_time,
            "symbol_count": n_symbols,
            "features_standardized": len(FEATURE_REGISTRY),
            "composites_computed": len(COMPOSITE_DEFINITIONS),
        }

    def load_latest_context_bundle(self) -> dict:
        """加载最新 AI bundle。"""
        bundle = self.repository.load_latest_bundle()
        if not bundle:
            return {"status": "no_data", "as_of": self._utc_now_iso()}
        return bundle

    def _load_indicators(self, timeframe: str) -> pd.DataFrame:
        """从 technical_indicators 加载最近 30d 数据。"""
        rows = self.repository.fetch_technical_indicators(timeframe, MIN_BARS_30D)
        if not rows:
            return pd.DataFrame()
        return pd.DataFrame(rows)

    def _compute_composites(
        self,
        latest_zscores: dict[str, dict[str, float | None]],
        latest_pcts: dict[str, dict[str, float | None]],
        symbols: list[str],
        n_symbols: int,
        snapshot_time: str,
    ) -> list[dict]:
        """聚合组件 Z-score 为维度复合信号。"""
        composite_rows: list[dict] = []

        for comp_name, feature_names in COMPOSITE_DEFINITIONS.items():
            comp_zscores_by_symbol: dict[str, float | None] = {}

            for symbol in symbols:
                components_z = {
                    f: latest_zscores.get(f, {}).get(symbol)
                    for f in feature_names
                }
                components_p = {
                    f: latest_pcts.get(f, {}).get(symbol)
                    for f in feature_names
                }
                comp_z = self.calculator.compute_composite(components_z)
                comp_p = self.calculator.compute_composite(components_p)
                comp_zscores_by_symbol[symbol] = comp_z

                valid_count = sum(
                    1 for v in components_z.values()
                    if v is not None
                )
                confidence = "high" if valid_count >= len(feature_names) * 0.6 else (
                    "medium" if valid_count >= 2 else "low"
                )

                composite_rows.append({
                    "snapshot_time": snapshot_time,
                    "symbol": symbol,
                    "composite_name": comp_name,
                    "composite_zscore": comp_z,
                    "composite_percentile": comp_p,
                    "cross_asset_rank": None,
                    "cross_asset_rank_total": n_symbols,
                    "regime_label": self.calculator.classify_regime(comp_z),
                    "confidence": confidence,
                    "component_count": valid_count,
                    "component_names": "|".join(feature_names),
                })

            # 复合信号跨资产排名
            ranks = self.calculator.cross_asset_rank(comp_zscores_by_symbol)
            for row in composite_rows:
                if row["composite_name"] == comp_name:
                    row["cross_asset_rank"] = ranks.get(row["symbol"])

        return composite_rows

    def _build_ai_bundle(
        self,
        detail_rows: list[dict],
        composite_rows: list[dict],
        symbols: list[str],
        snapshot_time: str,
    ) -> dict:
        """构建 AI 消费用结构化 bundle。"""
        # 按资产组织
        assets: list[dict] = []
        for symbol in symbols:
            sym_details = [r for r in detail_rows if r["symbol"] == symbol]
            sym_composites = [r for r in composite_rows if r["symbol"] == symbol]

            composites_dict = {}
            for c in sym_composites:
                composites_dict[c["composite_name"]] = {
                    "zscore": c["composite_zscore"],
                    "percentile": c["composite_percentile"],
                    "rank": c["cross_asset_rank"],
                    "regime": c["regime_label"],
                    "confidence": c["confidence"],
                }

            # 只输出 |zscore_30d| > 1.5 的显著特征
            notable = [
                {
                    "feature": r["feature_name"],
                    "zscore_30d": r["zscore_30d"],
                    "percentile_30d": r["percentile_30d"],
                    "rank": r["cross_asset_rank"],
                    "regime": r["regime_label"],
                }
                for r in sym_details
                if r["zscore_30d"] is not None and abs(r["zscore_30d"]) > 1.5
            ]
            notable.sort(key=lambda x: abs(x["zscore_30d"] or 0), reverse=True)

            # 整体极端度 = 最大复合 |zscore|
            max_extremity = max(
                (abs(c["composite_zscore"]) for c in sym_composites if c["composite_zscore"] is not None),
                default=0.0,
            )

            assets.append({
                "symbol": symbol,
                "sector": get_symbol_sector(symbol),
                "tier": str(get_symbol_tier(symbol).value) if get_symbol_tier(symbol) else None,
                "composites": composites_dict,
                "notable_features": notable[:10],
                "overall_extremity_score": round(max_extremity, 3),
            })

        assets.sort(key=lambda a: a["overall_extremity_score"], reverse=True)

        # Regime 分布统计
        regime_dist: dict[str, int] = {}
        for r in detail_rows:
            label = r["regime_label"]
            regime_dist[label] = regime_dist.get(label, 0) + 1

        # 最极端复合维度
        all_composites = [r for r in composite_rows if r["composite_zscore"] is not None]
        all_composites.sort(key=lambda x: abs(x["composite_zscore"] or 0), reverse=True)
        most_extreme = []
        seen_composites: set[str] = set()
        for c in all_composites:
            if c["composite_name"] not in seen_composites:
                seen_composites.add(c["composite_name"])
                most_extreme.append({
                    "composite": c["composite_name"],
                    "most_extreme_asset": c["symbol"],
                    "zscore": c["composite_zscore"],
                    "regime": c["regime_label"],
                })
            if len(most_extreme) >= 4:
                break

        # 板块聚合
        sectors: list[dict] = []
        for sector, sector_symbols in SECTOR_DEFINITIONS.items():
            sector_composites: dict[str, list[float]] = {}
            for c in composite_rows:
                if c["symbol"] in sector_symbols and c["composite_zscore"] is not None:
                    sector_composites.setdefault(c["composite_name"], []).append(c["composite_zscore"])
            if not sector_composites:
                continue
            sector_entry: dict = {"sector": sector, "assets": sector_symbols}
            for comp_name, values in sector_composites.items():
                sector_entry[f"avg_{comp_name}_zscore"] = round(float(np.mean(values)), 3)
            sectors.append(sector_entry)

        # 置信度摘要
        low_conf_assets = sorted(set(
            r["symbol"] for r in detail_rows if r["confidence"] == "low"
        ))

        return {
            "as_of": snapshot_time,
            "status": "ready",
            "symbol_count": len(symbols),
            "feature_count": len(FEATURE_REGISTRY),
            "composite_count": len(COMPOSITE_DEFINITIONS),
            "market_extremes": {
                "most_extreme_composites": most_extreme,
                "regime_distribution": regime_dist,
            },
            "assets": assets,
            "sectors": sectors,
            "data_quality": {
                "low_confidence_count": len(low_conf_assets),
                "low_confidence_assets": low_conf_assets,
            },
        }

    def close(self):
        self.db.close()
