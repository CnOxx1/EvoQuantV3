"""跨链桥净流采集器 — 使用 DeFiLlama Bridges 公开 API。"""

from __future__ import annotations

from datetime import datetime, timezone

from loguru import logger

from data_layer.onchain_data.client import OnchainDataClient
from data_layer.onchain_data.models import OnchainTimeSeriesPoint, dump_json
from data_layer.onchain_data.sources import load_onchain_factors


class BridgeNetflowCollector:
    """跨链桥净流采集器。

    数据源: DeFiLlama Bridges API (免费，无需 API key)
    端点: https://bridges.llama.fi/bridges
    端点: https://bridges.llama.fi/bridgevolume/{chain}
    """

    DEFILLAMA_BRIDGES_URL = "https://bridges.llama.fi/bridges"
    DEFILLAMA_BRIDGE_VOLUME_URL = "https://bridges.llama.fi/bridgevolume/{chain}"

    # DeFiLlama chain name → 我们的 entity_key
    CHAIN_MAP = {
        "Ethereum": "ETHEREUM",
        "Solana": "SOLANA",
        "Arbitrum": "ARBITRUM",
        "Base": "BASE",
        "Sui": "SUI",
        "BSC": "BSC",
        "Polygon": "POLYGON",
        "Avalanche": "AVALANCHE",
        "Optimism": "OPTIMISM",
    }

    # 用于 bridgevolume API 的链名（小写）
    CHAIN_SLUG_MAP = {
        "ETHEREUM": "Ethereum",
        "SOLANA": "Solana",
        "ARBITRUM": "Arbitrum",
        "BASE": "Base",
        "SUI": "Sui",
        "BSC": "BSC",
        "POLYGON": "Polygon",
        "AVALANCHE": "Avalanche",
        "OPTIMISM": "Optimism",
    }

    FIELD_FACTOR_MAP = {
        "bridge_inflow": "bridge_inflow",
        "bridge_outflow": "bridge_outflow",
        "bridge_netflow": "bridge_netflow",
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
                source_names=["bridge_netflow"], enabled_only=False
            )
        }
        if not factors:
            return []

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        allowed = set(k.upper() for k in (entity_keys or []))
        points: list[OnchainTimeSeriesPoint] = []

        inflow_factor = factors.get("bridge_inflow")
        outflow_factor = factors.get("bridge_outflow")
        netflow_factor = factors.get("bridge_netflow")

        # 获取各链的桥接量数据
        target_chains = list(self.CHAIN_SLUG_MAP.items())
        if allowed:
            target_chains = [(k, v) for k, v in target_chains if k in allowed]

        for entity_key, chain_slug in target_chains:
            url = self.DEFILLAMA_BRIDGE_VOLUME_URL.format(chain=chain_slug)
            try:
                payload = self.client._fetch_json(url)
            except Exception as exc:
                logger.warning(f"桥接数据获取失败 [{chain_slug}]: {exc}")
                continue

            if not isinstance(payload, list) or not payload:
                continue

            # 取最近一条记录（最新日期）
            latest = payload[-1] if payload else None
            if not latest:
                continue

            deposit = float(latest.get("depositUSD") or 0)
            withdraw = float(latest.get("withdrawUSD") or 0)
            netflow = deposit - withdraw

            if inflow_factor and deposit > 0:
                points.append(OnchainTimeSeriesPoint(
                    factor_id="bridge_inflow",
                    category=inflow_factor.category,
                    factor_type=inflow_factor.factor_type,
                    entity_type="chain",
                    entity_key=entity_key,
                    interval=interval or "1d",
                    observation_time=now,
                    value=deposit,
                    unit="usd",
                    quality_flag="ok",
                    dimensions_json={},
                    config_version=inflow_factor.config_version,
                    source_name="bridge_netflow",
                    source_symbol="defillama",
                    raw_payload_json=dump_json({
                        "chain": chain_slug, "deposit": deposit,
                        "withdraw": withdraw,
                    }),
                ))

            if outflow_factor and withdraw > 0:
                points.append(OnchainTimeSeriesPoint(
                    factor_id="bridge_outflow",
                    category=outflow_factor.category,
                    factor_type=outflow_factor.factor_type,
                    entity_type="chain",
                    entity_key=entity_key,
                    interval=interval or "1d",
                    observation_time=now,
                    value=withdraw,
                    unit="usd",
                    quality_flag="ok",
                    dimensions_json={},
                    config_version=outflow_factor.config_version,
                    source_name="bridge_netflow",
                    source_symbol="defillama",
                    raw_payload_json=dump_json({
                        "chain": chain_slug, "withdraw": withdraw,
                    }),
                ))

            if netflow_factor:
                points.append(OnchainTimeSeriesPoint(
                    factor_id="bridge_netflow",
                    category=netflow_factor.category,
                    factor_type=netflow_factor.factor_type,
                    entity_type="chain",
                    entity_key=entity_key,
                    interval=interval or "1d",
                    observation_time=now,
                    value=netflow,
                    unit="usd",
                    quality_flag="ok",
                    dimensions_json={},
                    config_version=netflow_factor.config_version,
                    source_name="bridge_netflow",
                    source_symbol="defillama",
                    raw_payload_json=dump_json({
                        "chain": chain_slug, "netflow": netflow,
                    }),
                ))

        return points
