"""DeFi 收益率采集器 — DeFiLlama Yields API (免费，无需 API key)。

稳定币收益率中位数是流动性松紧的领先指标：
- 收益率上升 → 链上杠杆需求增加 → 市场偏多
- 收益率下降 → 资金撤出 DeFi → 市场偏空/避险
"""

from __future__ import annotations

import statistics
from datetime import datetime, timezone

from loguru import logger

from data_layer.onchain_data.client import OnchainDataClient
from data_layer.onchain_data.models import OnchainTimeSeriesPoint, dump_json
from data_layer.onchain_data.sources import load_onchain_factors


class DefiYieldsCollector:
    """DeFi 收益率采集器。

    数据源: DeFiLlama Yields API (免费，无需 API key)
    端点: https://yields.llama.fi/pools
    """

    YIELDS_URL = "https://yields.llama.fi/pools"
    MIN_TVL_USD = 10_000_000  # 只统计 TVL > $10M 的池子

    def __init__(self, client: OnchainDataClient):
        self.client = client

    def collect(
        self,
        entity_keys: list[str] | None = None,
        interval: str | None = None,
        lookback_hours: int | None = None,
    ) -> list[OnchainTimeSeriesPoint]:
        factors = {
            f.factor_id: f
            for f in load_onchain_factors(
                source_names=["defi_yields"], enabled_only=False
            )
        }
        if not factors:
            return []

        try:
            payload = self.client._fetch_json(self.YIELDS_URL)
        except Exception as exc:
            logger.warning(f"DeFiLlama Yields 数据获取失败: {exc}")
            return []

        if not isinstance(payload, dict):
            return []

        pools = payload.get("data") or []
        if not pools:
            return []

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        points: list[OnchainTimeSeriesPoint] = []

        # 筛选高 TVL 稳定币池子计算中位数收益率
        stable_apys = [
            float(p["apy"])
            for p in pools
            if p.get("stablecoin")
            and float(p.get("tvlUsd") or 0) >= self.MIN_TVL_USD
            and p.get("apy") is not None
            and float(p["apy"]) > 0
        ]

        # 计算全市场 DeFi TVL
        total_tvl = sum(
            float(p.get("tvlUsd") or 0) for p in pools
        )

        median_factor = factors.get("defi_stablecoin_yield_median")
        if median_factor and stable_apys:
            median_apy = statistics.median(stable_apys)
            points.append(OnchainTimeSeriesPoint(
                factor_id="defi_stablecoin_yield_median",
                category=median_factor.category,
                factor_type=median_factor.factor_type,
                entity_type="market",
                entity_key="CRYPTO",
                interval=interval or "1d",
                observation_time=now,
                value=round(median_apy, 4),
                unit="percent",
                quality_flag="ok",
                dimensions_json={"pool_count": len(stable_apys)},
                config_version=median_factor.config_version,
                source_name="defi_yields",
                source_symbol="defillama",
                raw_payload_json=dump_json({
                    "median_apy": round(median_apy, 4),
                    "pool_count": len(stable_apys),
                    "min_tvl_filter": self.MIN_TVL_USD,
                }),
            ))

        tvl_factor = factors.get("defi_total_tvl")
        if tvl_factor and total_tvl > 0:
            points.append(OnchainTimeSeriesPoint(
                factor_id="defi_total_tvl",
                category=tvl_factor.category,
                factor_type=tvl_factor.factor_type,
                entity_type="market",
                entity_key="CRYPTO",
                interval=interval or "1d",
                observation_time=now,
                value=total_tvl,
                unit="usd",
                quality_flag="ok",
                dimensions_json={},
                config_version=tvl_factor.config_version,
                source_name="defi_yields",
                source_symbol="defillama",
                raw_payload_json=dump_json({
                    "total_tvl": total_tvl,
                    "total_pools": len(pools),
                }),
            ))

        return points
