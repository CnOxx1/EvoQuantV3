"""DEX 交易量采集器 — 使用 DeFiLlama 公开 API。"""

from __future__ import annotations

from datetime import datetime, timezone

from data_layer.onchain_data.client import OnchainDataClient
from data_layer.onchain_data.models import OnchainTimeSeriesPoint, dump_json
from data_layer.onchain_data.sources import load_onchain_factors


class DexVolumeCollector:
    """DEX 交易量采集器。

    数据源: DeFiLlama DEX Overview API (免费，无需 API key)
    端点: https://api.llama.fi/overview/dexs
    """

    DEFILLAMA_DEX_URL = "https://api.llama.fi/overview/dexs"

    # DeFiLlama chain name → 我们的 entity_key 映射
    CHAIN_MAP = {
        "ethereum": "ETHEREUM",
        "solana": "SOLANA",
        "arbitrum": "ARBITRUM",
        "base": "BASE",
        "sui": "SUI",
        "bsc": "BSC",
        "polygon": "POLYGON",
        "avalanche": "AVALANCHE",
        "optimism": "OPTIMISM",
    }

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
                source_names=["dex_volume"], enabled_only=False
            )
        }
        if not factors:
            return []

        payload = self.client._fetch_json(self.DEFILLAMA_DEX_URL)
        if not isinstance(payload, dict):
            return []

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        allowed = set(k.upper() for k in (entity_keys or []))
        points: list[OnchainTimeSeriesPoint] = []

        # 解析 totalDataChartBreakdown (按链的每日 DEX 交易量)
        chain_volumes = payload.get("allChains") or []
        total_24h = payload.get("total24h") or 0
        total_7d = payload.get("total7d") or 0
        change_1d = payload.get("change_1d") or 0

        # 按链聚合: 从 protocols 列表中提取各链 24h volume
        chain_24h: dict[str, float] = {}
        for protocol in payload.get("protocols") or []:
            chains = protocol.get("chains") or []
            vol_24h = float(protocol.get("total24h") or 0)
            chain_breakdown = protocol.get("breakdown") or {}
            for chain_name in chains:
                entity = self.CHAIN_MAP.get(chain_name.lower())
                if not entity:
                    continue
                if allowed and entity not in allowed:
                    continue
                # 尝试从 breakdown 获取精确值
                chain_data = chain_breakdown.get(chain_name) or {}
                chain_vol = sum(float(v) for v in chain_data.values()) if chain_data else 0
                if chain_vol > 0:
                    chain_24h[entity] = chain_24h.get(entity, 0) + chain_vol
                elif len(chains) == 1:
                    chain_24h[entity] = chain_24h.get(entity, 0) + vol_24h

        # 生成 points
        vol_factor = factors.get("dex_volume_24h")
        change_factor = factors.get("dex_volume_change_1d")

        for entity, volume in chain_24h.items():
            if vol_factor:
                points.append(OnchainTimeSeriesPoint(
                    factor_id="dex_volume_24h",
                    category=vol_factor.category,
                    factor_type=vol_factor.factor_type,
                    entity_type="chain",
                    entity_key=entity,
                    interval=interval or "1d",
                    observation_time=now,
                    value=volume,
                    unit="usd",
                    quality_flag="ok",
                    dimensions_json={},
                    config_version=vol_factor.config_version,
                    source_name="dex_volume",
                    source_symbol="defillama",
                    raw_payload_json=dump_json({"chain": entity, "volume_24h": volume}),
                ))

        # 全市场汇总
        if vol_factor and total_24h:
            points.append(OnchainTimeSeriesPoint(
                factor_id="dex_volume_24h",
                category=vol_factor.category,
                factor_type=vol_factor.factor_type,
                entity_type="chain",
                entity_key="ALL",
                interval=interval or "1d",
                observation_time=now,
                value=float(total_24h),
                unit="usd",
                quality_flag="ok",
                dimensions_json={"total_7d": total_7d},
                config_version=vol_factor.config_version,
                source_name="dex_volume",
                source_symbol="defillama",
                raw_payload_json=dump_json({"total_24h": total_24h, "total_7d": total_7d}),
            ))

        if change_factor and change_1d:
            points.append(OnchainTimeSeriesPoint(
                factor_id="dex_volume_change_1d",
                category=change_factor.category,
                factor_type=change_factor.factor_type,
                entity_type="chain",
                entity_key="ALL",
                interval=interval or "1d",
                observation_time=now,
                value=float(change_1d),
                unit="percent",
                quality_flag="ok",
                dimensions_json={},
                config_version=change_factor.config_version,
                source_name="dex_volume",
                source_symbol="defillama",
                raw_payload_json=dump_json({"change_1d": change_1d}),
            ))

        return points
