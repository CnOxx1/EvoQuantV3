"""协议 TVL 采集器 — 使用 DeFiLlama 公开 API。"""

from __future__ import annotations

from datetime import datetime, timezone

from data_layer.onchain_data.client import OnchainDataClient
from data_layer.onchain_data.models import OnchainTimeSeriesPoint, dump_json
from data_layer.onchain_data.sources import load_onchain_factors


class ProtocolTVLCollector:
    """协议 TVL 采集器。

    数据源: DeFiLlama Protocols API (免费，无需 API key)
    端点: https://api.llama.fi/protocols
    """

    DEFILLAMA_PROTOCOLS_URL = "https://api.llama.fi/protocols"

    # DeFiLlama slug → 我们的 entity_key
    PROTOCOL_MAP = {
        "aave": "AAVE",
        "uniswap": "UNISWAP",
        "jupiter": "JUPITER",
        "cetus-amm": "CETUS",
        "lido": "LIDO",
        "makerdao": "MAKERDAO",
        "curve-dex": "CURVE",
        "raydium": "RAYDIUM",
        "pancakeswap": "PANCAKESWAP",
        "compound-finance": "COMPOUND",
    }

    FIELD_FACTOR_MAP = {
        "protocol_tvl": "protocol_tvl",
        "protocol_tvl_change_24h": "protocol_tvl_change_24h",
        "protocol_tvl_change_7d": "protocol_tvl_change_7d",
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
                source_names=["protocol_tvl"], enabled_only=False
            )
        }
        if not factors:
            return []

        payload = self.client._fetch_json(self.DEFILLAMA_PROTOCOLS_URL)
        if not isinstance(payload, list):
            return []

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        allowed = set(k.upper() for k in (entity_keys or []))
        points: list[OnchainTimeSeriesPoint] = []

        tvl_factor = factors.get("protocol_tvl")
        change_24h_factor = factors.get("protocol_tvl_change_24h")
        change_7d_factor = factors.get("protocol_tvl_change_7d")

        for protocol in payload:
            slug = str(protocol.get("slug") or "").lower()
            entity = self.PROTOCOL_MAP.get(slug)
            if not entity:
                continue
            if allowed and entity not in allowed:
                continue

            tvl = float(protocol.get("tvl") or 0)
            if tvl <= 0:
                continue

            change_1d = protocol.get("change_1d")
            change_7d = protocol.get("change_7d")

            if tvl_factor:
                points.append(OnchainTimeSeriesPoint(
                    factor_id="protocol_tvl",
                    category=tvl_factor.category,
                    factor_type=tvl_factor.factor_type,
                    entity_type="protocol",
                    entity_key=entity,
                    interval=interval or "1d",
                    observation_time=now,
                    value=tvl,
                    unit="usd",
                    quality_flag="ok",
                    dimensions_json={"name": protocol.get("name", "")},
                    config_version=tvl_factor.config_version,
                    source_name="protocol_tvl",
                    source_symbol="defillama",
                    raw_payload_json=dump_json({
                        "slug": slug, "tvl": tvl,
                        "change_1d": change_1d, "change_7d": change_7d,
                    }),
                ))

            if change_24h_factor and change_1d is not None:
                points.append(OnchainTimeSeriesPoint(
                    factor_id="protocol_tvl_change_24h",
                    category=change_24h_factor.category,
                    factor_type=change_24h_factor.factor_type,
                    entity_type="protocol",
                    entity_key=entity,
                    interval=interval or "1d",
                    observation_time=now,
                    value=float(change_1d),
                    unit="percent",
                    quality_flag="ok",
                    dimensions_json={},
                    config_version=change_24h_factor.config_version,
                    source_name="protocol_tvl",
                    source_symbol="defillama",
                    raw_payload_json=dump_json({"change_1d": change_1d}),
                ))

            if change_7d_factor and change_7d is not None:
                points.append(OnchainTimeSeriesPoint(
                    factor_id="protocol_tvl_change_7d",
                    category=change_7d_factor.category,
                    factor_type=change_7d_factor.factor_type,
                    entity_type="protocol",
                    entity_key=entity,
                    interval=interval or "1d",
                    observation_time=now,
                    value=float(change_7d),
                    unit="percent",
                    quality_flag="ok",
                    dimensions_json={},
                    config_version=change_7d_factor.config_version,
                    source_name="protocol_tvl",
                    source_symbol="defillama",
                    raw_payload_json=dump_json({"change_7d": change_7d}),
                ))

        return points
