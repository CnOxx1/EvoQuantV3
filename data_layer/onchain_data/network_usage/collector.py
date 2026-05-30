"""链使用率采集器 — 使用 DeFiLlama 公开 API。"""

from __future__ import annotations

from datetime import datetime, timezone

from loguru import logger

from data_layer.onchain_data.client import OnchainDataClient
from data_layer.onchain_data.models import OnchainTimeSeriesPoint, dump_json
from data_layer.onchain_data.sources import load_onchain_factors


class NetworkUsageCollector:
    """链使用率采集器。

    数据源: DeFiLlama Fees/Revenue API (免费，无需 API key)
    端点: https://api.llama.fi/overview/fees
    """

    DEFILLAMA_FEES_URL = "https://api.llama.fi/overview/fees"

    # DeFiLlama chain name → 我们的 entity_key
    CHAIN_MAP = {
        "ethereum": "ETHEREUM",
        "bitcoin": "BITCOIN",
        "solana": "SOLANA",
        "arbitrum": "ARBITRUM",
        "base": "BASE",
        "sui": "SUI",
        "bsc": "BSC",
        "polygon": "POLYGON",
        "avalanche": "AVALANCHE",
        "optimism": "OPTIMISM",
    }

    FIELD_FACTOR_MAP = {
        "active_addresses": "active_addresses",
        "transaction_count": "transaction_count",
        "fees_paid": "fees_paid",
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
                source_names=["network_usage"], enabled_only=False
            )
        }
        if not factors:
            return []

        payload = self.client._fetch_json(self.DEFILLAMA_FEES_URL)
        if not isinstance(payload, dict):
            return []

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        allowed = set(k.upper() for k in (entity_keys or []))
        points: list[OnchainTimeSeriesPoint] = []

        fees_factor = factors.get("fees_paid")

        # 按链聚合手续费数据
        chain_fees: dict[str, float] = {}
        for protocol in payload.get("protocols") or []:
            chains = protocol.get("chains") or []
            total_24h = float(protocol.get("total24h") or 0)
            breakdown = protocol.get("breakdown") or {}
            for chain_name in chains:
                entity = self.CHAIN_MAP.get(chain_name.lower())
                if not entity:
                    continue
                if allowed and entity not in allowed:
                    continue
                chain_data = breakdown.get(chain_name) or {}
                chain_fee = sum(float(v) for v in chain_data.values()) if chain_data else 0
                if chain_fee > 0:
                    chain_fees[entity] = chain_fees.get(entity, 0) + chain_fee
                elif len(chains) == 1 and total_24h > 0:
                    chain_fees[entity] = chain_fees.get(entity, 0) + total_24h

        # 生成 fees_paid points
        for entity, fee_value in chain_fees.items():
            if fees_factor and fee_value > 0:
                points.append(OnchainTimeSeriesPoint(
                    factor_id="fees_paid",
                    category=fees_factor.category,
                    factor_type=fees_factor.factor_type,
                    entity_type="chain",
                    entity_key=entity,
                    interval=interval or "1d",
                    observation_time=now,
                    value=fee_value,
                    unit="usd",
                    quality_flag="ok",
                    dimensions_json={},
                    config_version=fees_factor.config_version,
                    source_name="network_usage",
                    source_symbol="defillama",
                    raw_payload_json=dump_json({
                        "chain": entity, "fees_24h": fee_value,
                    }),
                ))

        # 全市场汇总
        total_fees = payload.get("total24h")
        if fees_factor and total_fees:
            points.append(OnchainTimeSeriesPoint(
                factor_id="fees_paid",
                category=fees_factor.category,
                factor_type=fees_factor.factor_type,
                entity_type="chain",
                entity_key="ALL",
                interval=interval or "1d",
                observation_time=now,
                value=float(total_fees),
                unit="usd",
                quality_flag="ok",
                dimensions_json={"scope": "all_chains"},
                config_version=fees_factor.config_version,
                source_name="network_usage",
                source_symbol="defillama",
                raw_payload_json=dump_json({"total_fees_24h": total_fees}),
            ))

        return points
