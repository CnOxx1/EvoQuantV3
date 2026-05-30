"""稳定币供给流向采集器 — 使用 DeFiLlama 公开 API。"""

from __future__ import annotations

from datetime import datetime, timezone

from data_layer.onchain_data.client import OnchainDataClient
from data_layer.onchain_data.models import OnchainTimeSeriesPoint, dump_json
from data_layer.onchain_data.sources import load_onchain_factors


class StablecoinSupplyCollector:
    """稳定币市值与流向采集器。

    数据源: DeFiLlama Stablecoins API (免费，无需 API key)
    端点: https://stablecoins.llama.fi/stablecoins?includePrices=true
    """

    DEFILLAMA_STABLECOINS_URL = (
        "https://stablecoins.llama.fi/stablecoins?includePrices=true"
    )

    # DeFiLlama symbol → 我们的 entity_key
    SYMBOL_MAP = {
        "USDT": "USDT",
        "USDC": "USDC",
        "DAI": "DAI",
        "FDUSD": "FDUSD",
        "USDE": "USDE",
        "TUSD": "TUSD",
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
                source_names=["stablecoin_supply"], enabled_only=False
            )
        }
        if not factors:
            return []

        payload = self.client._fetch_json(self.DEFILLAMA_STABLECOINS_URL)
        if not isinstance(payload, dict):
            return []

        stablecoins = payload.get("peggedAssets") or []
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        allowed = set(k.upper() for k in (entity_keys or []))
        points: list[OnchainTimeSeriesPoint] = []

        mcap_factor = factors.get("stablecoin_mcap")
        change_factor = factors.get("stablecoin_mcap_change_7d")

        for coin in stablecoins:
            symbol = str(coin.get("symbol") or "").upper()
            entity = self.SYMBOL_MAP.get(symbol)
            if not entity:
                continue
            if allowed and entity not in allowed:
                continue

            # 当前市值
            circulating = coin.get("circulating") or {}
            mcap = float(circulating.get("peggedUSD") or 0)
            if mcap <= 0:
                continue

            # 7d 变化
            mcap_change = coin.get("circulatingPrevDay") or {}
            prev_mcap = float(mcap_change.get("peggedUSD") or 0)
            change_7d_pct = 0.0
            mcap_prev_week = coin.get("circulatingPrevWeek") or {}
            prev_week_val = float(mcap_prev_week.get("peggedUSD") or 0)
            if prev_week_val > 0:
                change_7d_pct = ((mcap - prev_week_val) / prev_week_val) * 100

            if mcap_factor:
                points.append(OnchainTimeSeriesPoint(
                    factor_id="stablecoin_mcap",
                    category=mcap_factor.category,
                    factor_type=mcap_factor.factor_type,
                    entity_type="stablecoin_asset",
                    entity_key=entity,
                    interval=interval or "1d",
                    observation_time=now,
                    value=mcap,
                    unit="usd",
                    quality_flag="ok",
                    dimensions_json={"name": coin.get("name", "")},
                    config_version=mcap_factor.config_version,
                    source_name="stablecoin_supply",
                    source_symbol="defillama",
                    raw_payload_json=dump_json({
                        "symbol": symbol, "mcap": mcap,
                        "prev_day": prev_mcap, "prev_week": prev_week_val,
                    }),
                ))

            if change_factor and prev_week_val > 0:
                points.append(OnchainTimeSeriesPoint(
                    factor_id="stablecoin_mcap_change_7d",
                    category=change_factor.category,
                    factor_type=change_factor.factor_type,
                    entity_type="stablecoin_asset",
                    entity_key=entity,
                    interval=interval or "1d",
                    observation_time=now,
                    value=change_7d_pct,
                    unit="percent",
                    quality_flag="ok",
                    dimensions_json={},
                    config_version=change_factor.config_version,
                    source_name="stablecoin_supply",
                    source_symbol="defillama",
                    raw_payload_json=dump_json({
                        "symbol": symbol, "change_7d_pct": change_7d_pct,
                    }),
                ))

        return points
