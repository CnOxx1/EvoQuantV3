from datetime import datetime

from data_layer.options_data.base import OptionsCollectorBase
from data_layer.options_data.client import OptionsDataClient
from data_layer.options_data.models import OptionsTimeSeriesPoint, dump_json
from data_layer.options_data.sources import (
    load_options_factors,
    load_options_sources,
)


class FlowActivityCollector(OptionsCollectorBase):
    """期权增量成交流与开仓意图采集器。"""

    def __init__(self, client: OptionsDataClient, db):
        super().__init__(db)
        self.client = client

    @staticmethod
    def _parse_time(value) -> datetime:
        if isinstance(value, datetime):
            return value
        text = str(value).strip()
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        return datetime.fromisoformat(text)

    @staticmethod
    def _first_number(row: dict, keys: tuple[str, ...]) -> float | None:
        for key in keys:
            value = row.get(key)
            if value is None or value == "":
                continue
            return float(value)
        return None

    @staticmethod
    def _normalize_raw_payload_json(row: dict) -> str | None:
        raw_payload = row.get("raw_payload_json")
        if isinstance(raw_payload, str):
            return raw_payload
        if isinstance(raw_payload, dict | list):
            return dump_json(raw_payload)
        return dump_json(row)

    @staticmethod
    def _ratio(value: float | None, total: float | None) -> float | None:
        if value is None or total is None or total <= 0:
            return None
        return value / total

    def fetch_recent_points(
        self,
        entity_keys: list[str] | None = None,
        interval: str | None = None,
        lookback_hours: int | None = None,
    ) -> list[OptionsTimeSeriesPoint]:
        source = load_options_sources(
            source_names=["flow_activity"],
            enabled_only=False,
        )[0]
        factors = {
            factor.factor_id: factor
            for factor in load_options_factors(
                source_names=["flow_activity"],
                enabled_only=False,
            )
        }
        rows = self.client.fetch_flow_activity_snapshots(
            source,
            entity_keys=entity_keys,
            interval=interval or source.default_interval,
            lookback_hours=lookback_hours,
        )
        points: list[OptionsTimeSeriesPoint] = []
        for row in rows:
            observation_time = self._parse_time(row["observation_time"])
            row_interval = str(row.get("interval") or interval or source.default_interval)
            total_premium = self._first_number(
                row,
                (
                    "total_premium_notional",
                    "total_options_premium_notional",
                    "total_premium",
                ),
            )
            call_buyer_premium = self._first_number(
                row,
                (
                    "call_buyer_initiated_premium",
                    "call_buy_premium",
                    "call_aggressive_buy_premium",
                ),
            )
            put_buyer_premium = self._first_number(
                row,
                (
                    "put_buyer_initiated_premium",
                    "put_buy_premium",
                    "put_aggressive_buy_premium",
                ),
            )
            call_seller_premium = self._first_number(
                row,
                (
                    "call_seller_initiated_premium",
                    "call_sell_premium",
                    "call_aggressive_sell_premium",
                ),
            )
            put_seller_premium = self._first_number(
                row,
                (
                    "put_seller_initiated_premium",
                    "put_sell_premium",
                    "put_aggressive_sell_premium",
                ),
            )
            opening_premium = self._first_number(
                row,
                (
                    "opening_premium_notional",
                    "opening_trade_premium_notional",
                    "opening_premium",
                ),
            )
            near_expiry_premium = self._first_number(
                row,
                (
                    "near_expiry_premium_notional",
                    "near_expiry_trade_premium_notional",
                    "near_expiry_premium",
                ),
            )
            block_trade_premium = self._first_number(
                row,
                (
                    "block_trade_premium_notional",
                    "block_premium_notional",
                    "block_trade_premium",
                ),
            )

            call_buyer_premium_share = self._first_number(
                row,
                ("call_buyer_premium_share",),
            )
            if call_buyer_premium_share is None:
                call_buyer_premium_share = self._ratio(call_buyer_premium, total_premium)

            put_buyer_premium_share = self._first_number(
                row,
                ("put_buyer_premium_share",),
            )
            if put_buyer_premium_share is None:
                put_buyer_premium_share = self._ratio(put_buyer_premium, total_premium)

            net_call_premium_flow_ratio = self._first_number(
                row,
                ("net_call_premium_flow_ratio",),
            )
            if (
                net_call_premium_flow_ratio is None
                and call_buyer_premium is not None
                and call_seller_premium is not None
                and (total_premium or 0.0) > 0.0
            ):
                net_call_premium_flow_ratio = (
                    call_buyer_premium - call_seller_premium
                ) / total_premium

            net_put_premium_flow_ratio = self._first_number(
                row,
                ("net_put_premium_flow_ratio",),
            )
            if (
                net_put_premium_flow_ratio is None
                and put_buyer_premium is not None
                and put_seller_premium is not None
                and (total_premium or 0.0) > 0.0
            ):
                net_put_premium_flow_ratio = (
                    put_buyer_premium - put_seller_premium
                ) / total_premium

            opening_flow_share = self._first_number(row, ("opening_flow_share",))
            if opening_flow_share is None:
                opening_flow_share = self._ratio(opening_premium, total_premium)

            near_expiry_flow_share = self._first_number(row, ("near_expiry_flow_share",))
            if near_expiry_flow_share is None:
                near_expiry_flow_share = self._ratio(near_expiry_premium, total_premium)

            block_trade_flow_share = self._first_number(row, ("block_trade_flow_share",))
            if block_trade_flow_share is None:
                block_trade_flow_share = self._ratio(block_trade_premium, total_premium)

            factor_rows = [
                (
                    "options_call_buyer_premium_share",
                    call_buyer_premium_share,
                    {"metric": "call_buyer_premium_share"},
                ),
                (
                    "options_put_buyer_premium_share",
                    put_buyer_premium_share,
                    {"metric": "put_buyer_premium_share"},
                ),
                (
                    "options_net_call_premium_flow_ratio",
                    net_call_premium_flow_ratio,
                    {"metric": "net_call_premium_flow_ratio"},
                ),
                (
                    "options_net_put_premium_flow_ratio",
                    net_put_premium_flow_ratio,
                    {"metric": "net_put_premium_flow_ratio"},
                ),
                (
                    "options_opening_flow_share",
                    opening_flow_share,
                    {"metric": "opening_flow_share"},
                ),
                (
                    "options_near_expiry_flow_share",
                    near_expiry_flow_share,
                    {"metric": "near_expiry_flow_share"},
                ),
                (
                    "options_block_trade_flow_share",
                    block_trade_flow_share,
                    {"metric": "block_trade_flow_share"},
                ),
            ]
            for factor_id, value, dimensions in factor_rows:
                if value is None:
                    continue
                factor = factors[factor_id]
                points.append(
                    OptionsTimeSeriesPoint(
                        factor_id=factor.factor_id,
                        category=factor.category,
                        factor_type=factor.factor_type,
                        entity_type=factor.entity_type,
                        entity_key=str(row["entity_key"]),
                        interval=row_interval,
                        observation_time=observation_time,
                        value=float(value),
                        unit=factor.unit or "",
                        quality_flag=str(row.get("quality_flag") or "ok"),
                        dimensions_json=dimensions,
                        config_version=str(row.get("config_version") or factor.config_version),
                        source_name=factor.source_name,
                        source_symbol=str(
                            row.get("source_symbol")
                            or f"{str(row['entity_key']).upper()}-OPTIONS-FLOW"
                        ),
                        raw_payload_json=self._normalize_raw_payload_json(row),
                    )
                )
        return points

    def collect(
        self,
        entity_keys: list[str] | None = None,
        interval: str | None = None,
        lookback_hours: int | None = None,
    ) -> list[OptionsTimeSeriesPoint]:
        points = self.fetch_recent_points(
            entity_keys=entity_keys,
            interval=interval,
            lookback_hours=lookback_hours,
        )
        if points:
            self.save_to_db(points)
        return points
