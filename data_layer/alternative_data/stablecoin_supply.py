from datetime import datetime, timedelta, timezone

from loguru import logger

from config.settings import ALTERNATIVE_CONFIG
from data_layer.alternative_data.base import AlternativeCollectorBase
from data_layer.alternative_data.client import AlternativeDataClient
from data_layer.alternative_data.models import AlternativeTimeSeriesPoint, dump_json, utc_now_naive
from data_layer.alternative_data.sources import load_alternative_factors, load_stablecoin_assets


class StablecoinSupplyCollector(AlternativeCollectorBase):
    """采集稳定币总供给、净变化与链上分布。"""

    EVENTIZATION_MODE = "snapshot_delta_inference"
    BRIDGE_ALLOCATION_METHOD = "proportional_reallocation_from_snapshot_delta"

    def __init__(self, client: AlternativeDataClient, db):
        super().__init__(db)
        self.client = client

    @staticmethod
    def _normalize_symbol(text: str | None) -> str:
        return (text or "").strip().upper()

    @staticmethod
    def _normalize_chain_key(text: str | None) -> str:
        normalized = (text or "").strip().lower().replace(" ", "_")
        return normalized.replace("-", "_")

    @staticmethod
    def _to_observation_time(value, default_time: datetime) -> datetime:
        if isinstance(value, datetime):
            if value.tzinfo is not None:
                return value.astimezone(timezone.utc).replace(tzinfo=None)
            return value
        parsed = AlternativeDataClient._parse_timestamp(value)
        return parsed or default_time

    @staticmethod
    def _extract_current_supply(asset_payload: dict) -> float | None:
        for key in (
            "circulating",
            "circulatingUSD",
            "supply",
            "totalCirculating",
            "totalCirculatingUSD",
            "mcap",
        ):
            value = AlternativeDataClient._extract_number(asset_payload.get(key))
            if value is not None:
                return float(value)
        return None

    @classmethod
    def _extract_chain_supplies(cls, asset_payload: dict) -> list[tuple[str, float]]:
        chain_rows: list[tuple[str, float]] = []
        chain_circulating = asset_payload.get("chainCirculating")
        if isinstance(chain_circulating, dict):
            for chain_name, value in chain_circulating.items():
                supply = AlternativeDataClient._extract_number(value)
                if supply is None or supply <= 0:
                    continue
                chain_rows.append((str(chain_name), float(supply)))
            return chain_rows

        if isinstance(chain_circulating, list):
            for item in chain_circulating:
                if not isinstance(item, dict):
                    continue
                chain_name = (
                    item.get("chain")
                    or item.get("name")
                    or item.get("chainName")
                )
                supply = AlternativeDataClient._extract_number(
                    item.get("circulating")
                    or item.get("supply")
                    or item.get("value")
                )
                if not chain_name or supply is None or supply <= 0:
                    continue
                chain_rows.append((str(chain_name), float(supply)))
            return chain_rows

        chains = asset_payload.get("chains")
        if isinstance(chains, list):
            chain_balances = asset_payload.get("chainBalances") or asset_payload.get("chain_distribution")
            if isinstance(chain_balances, list):
                for chain_name, value in zip(chains, chain_balances):
                    supply = AlternativeDataClient._extract_number(value)
                    if supply is None or supply <= 0:
                        continue
                    chain_rows.append((str(chain_name), float(supply)))
        return chain_rows

    @staticmethod
    def _build_point(
        factor,
        entity_type: str,
        entity_key: str,
        interval: str,
        observation_time: datetime,
        value: float,
        quality_flag: str,
        dimensions_json: dict[str, object],
        source_symbol: str,
        raw_payload: dict[str, object],
    ) -> AlternativeTimeSeriesPoint:
        return AlternativeTimeSeriesPoint(
            factor_id=factor.factor_id,
            category=factor.category,
            factor_type=factor.factor_type,
            entity_type=entity_type,
            entity_key=entity_key,
            interval=interval,
            observation_time=observation_time,
            value=float(value),
            unit=factor.unit,
            quality_flag=quality_flag,
            dimensions_json=dimensions_json,
            config_version=factor.config_version,
            source_name=factor.source_name,
            source_symbol=source_symbol,
            raw_payload_json=dump_json(raw_payload),
        )

    def _select_asset_payload(
        self,
        asset_config: dict[str, object],
        assets_payload: list[dict],
    ) -> dict | None:
        aliases = {
            self._normalize_symbol(asset_config["entity_key"]),
            *{
                self._normalize_symbol(alias)
                for alias in asset_config.get("aliases", [])
            },
        }

        matches: list[dict] = []
        for payload in assets_payload:
            symbol = self._normalize_symbol(
                payload.get("symbol") or payload.get("name")
            )
            if symbol in aliases:
                matches.append(payload)

        if not matches:
            return None
        matches.sort(
            key=lambda item: self._extract_current_supply(item) or 0.0,
            reverse=True,
        )
        return matches[0]

    @staticmethod
    def _find_baseline_record(
        records: list[dict],
        target_time: datetime,
        tolerance: timedelta,
    ) -> dict | None:
        best_record = None
        best_gap = None
        for record in records:
            gap = abs((record["timestamp"] - target_time).total_seconds())
            if best_gap is None or gap < best_gap:
                best_gap = gap
                best_record = record
        if best_record is None or best_gap is None:
            return None
        if best_gap > tolerance.total_seconds():
            return None
        return best_record

    @classmethod
    def _normalize_chain_history_snapshots(
        cls,
        rows: list[dict],
        default_time: datetime,
    ) -> list[dict]:
        snapshots_by_time: dict[datetime, dict[str, object]] = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            timestamp = cls._to_observation_time(
                row.get("timestamp")
                or row.get("date")
                or row.get("time")
                or row.get("datetime"),
                default_time,
            )
            chains_payload = row.get("chains") or []
            chains: list[dict[str, object]] = []
            for item in chains_payload:
                if not isinstance(item, dict):
                    continue
                chain_name = (
                    item.get("chain")
                    or item.get("name")
                    or item.get("chainName")
                )
                supply = AlternativeDataClient._extract_number(
                    item.get("supply")
                    or item.get("circulating")
                    or item.get("value")
                )
                if not chain_name or supply is None or supply <= 0:
                    continue
                chains.append(
                    {
                        "chain": str(chain_name),
                        "supply": float(supply),
                    }
                )
            if not chains:
                continue
            snapshots_by_time[timestamp] = {
                "timestamp": timestamp,
                "chains": chains,
            }
        return [
            snapshots_by_time[key]
            for key in sorted(snapshots_by_time)
        ]

    @classmethod
    def _chain_snapshot_maps(
        cls,
        snapshot: dict[str, object],
    ) -> tuple[dict[str, float], dict[str, str]]:
        supply_by_chain: dict[str, float] = {}
        display_by_chain: dict[str, str] = {}
        for item in snapshot.get("chains", []):
            if not isinstance(item, dict):
                continue
            chain_name = str(item.get("chain") or "")
            if not chain_name:
                continue
            chain_key = cls._normalize_chain_key(chain_name)
            supply = AlternativeDataClient._extract_number(item.get("supply"))
            if supply is None:
                continue
            supply_by_chain[chain_key] = float(supply)
            display_by_chain[chain_key] = chain_name
        return supply_by_chain, display_by_chain

    def _build_event_points(
        self,
        factor_map: dict[str, object],
        context: dict[str, object],
        latest_only: bool,
    ) -> list[AlternativeTimeSeriesPoint]:
        asset_config = context["asset_config"]
        asset_symbol = str(asset_config["entity_key"])
        asset_id = context["asset_id"]
        history = context["history"]
        chain_history = context.get("chain_history") or []
        source_symbol = f"stablecoin:{asset_id}"
        points: list[AlternativeTimeSeriesPoint] = []

        history_pairs = list(zip(history, history[1:]))
        chain_history_pairs = list(zip(chain_history, chain_history[1:]))
        if latest_only:
            history_pairs = history_pairs[-1:]
            chain_history_pairs = chain_history_pairs[-1:]

        asset_dimensions = {
            "aggregation_scope": "asset",
            "eventization_mode": self.EVENTIZATION_MODE,
        }
        for previous_row, current_row in history_pairs:
            observation_time = current_row["timestamp"]
            previous_supply = float(previous_row["supply"])
            current_supply = float(current_row["supply"])
            delta_supply = current_supply - previous_supply
            mint_volume = max(delta_supply, 0.0)
            burn_volume = max(-delta_supply, 0.0)
            common_payload = {
                "asset_id": asset_id,
                "asset": asset_symbol,
                "eventization_mode": self.EVENTIZATION_MODE,
                "previous_timestamp": previous_row["timestamp"].isoformat(),
                "current_timestamp": current_row["timestamp"].isoformat(),
                "previous_supply": previous_supply,
                "current_supply": current_supply,
                "delta_supply": delta_supply,
            }
            points.append(
                self._build_point(
                    factor=factor_map["stablecoin_mint_volume"],
                    entity_type="stablecoin_asset",
                    entity_key=asset_symbol,
                    interval="1d",
                    observation_time=observation_time,
                    value=mint_volume,
                    quality_flag="ok",
                    dimensions_json=asset_dimensions,
                    source_symbol=source_symbol,
                    raw_payload={
                        **common_payload,
                        "event_type": "mint",
                        "value": mint_volume,
                    },
                )
            )
            points.append(
                self._build_point(
                    factor=factor_map["stablecoin_burn_volume"],
                    entity_type="stablecoin_asset",
                    entity_key=asset_symbol,
                    interval="1d",
                    observation_time=observation_time,
                    value=burn_volume,
                    quality_flag="ok",
                    dimensions_json=asset_dimensions,
                    source_symbol=source_symbol,
                    raw_payload={
                        **common_payload,
                        "event_type": "burn",
                        "value": burn_volume,
                    },
                )
            )

        for previous_snapshot, current_snapshot in chain_history_pairs:
            observation_time = current_snapshot["timestamp"]
            previous_supply_by_chain, previous_display_by_chain = self._chain_snapshot_maps(
                previous_snapshot
            )
            current_supply_by_chain, current_display_by_chain = self._chain_snapshot_maps(
                current_snapshot
            )
            all_chain_keys = sorted(
                set(previous_supply_by_chain).union(current_supply_by_chain)
            )
            positive_deltas = {
                chain_key: max(
                    current_supply_by_chain.get(chain_key, 0.0)
                    - previous_supply_by_chain.get(chain_key, 0.0),
                    0.0,
                )
                for chain_key in all_chain_keys
            }
            negative_deltas = {
                chain_key: max(
                    previous_supply_by_chain.get(chain_key, 0.0)
                    - current_supply_by_chain.get(chain_key, 0.0),
                    0.0,
                )
                for chain_key in all_chain_keys
            }
            total_positive_delta = sum(positive_deltas.values())
            total_negative_delta = sum(negative_deltas.values())
            bridge_amount = min(total_positive_delta, total_negative_delta)
            chain_delta_map = {
                chain_key: (
                    current_supply_by_chain.get(chain_key, 0.0)
                    - previous_supply_by_chain.get(chain_key, 0.0)
                )
                for chain_key in all_chain_keys
            }
            matched_previous_total = self._find_baseline_record(
                history,
                previous_snapshot["timestamp"],
                tolerance=timedelta(days=2),
            )
            matched_current_total = self._find_baseline_record(
                history,
                current_snapshot["timestamp"],
                tolerance=timedelta(days=2),
            )
            total_supply_previous = (
                matched_previous_total["supply"]
                if matched_previous_total is not None
                else sum(previous_supply_by_chain.values())
            )
            total_supply_current = (
                matched_current_total["supply"]
                if matched_current_total is not None
                else sum(current_supply_by_chain.values())
            )

            for chain_key in all_chain_keys:
                bridge_inflow = 0.0
                bridge_outflow = 0.0
                if bridge_amount > 0 and total_positive_delta > 0:
                    bridge_inflow = (
                        bridge_amount
                        * positive_deltas[chain_key]
                        / total_positive_delta
                    )
                if bridge_amount > 0 and total_negative_delta > 0:
                    bridge_outflow = (
                        bridge_amount
                        * negative_deltas[chain_key]
                        / total_negative_delta
                    )
                chain_name = (
                    current_display_by_chain.get(chain_key)
                    or previous_display_by_chain.get(chain_key)
                    or chain_key
                )
                entity_key = f"{asset_symbol}:{chain_key}"
                chain_source_symbol = f"{source_symbol}:{chain_key}"
                chain_dimensions = {
                    "aggregation_scope": "asset_chain",
                    "asset": asset_symbol,
                    "chain": chain_key,
                    "eventization_mode": self.EVENTIZATION_MODE,
                }
                common_payload = {
                    "asset_id": asset_id,
                    "asset": asset_symbol,
                    "chain": chain_name,
                    "eventization_mode": self.EVENTIZATION_MODE,
                    "allocation_method": self.BRIDGE_ALLOCATION_METHOD,
                    "previous_timestamp": previous_snapshot["timestamp"].isoformat(),
                    "current_timestamp": current_snapshot["timestamp"].isoformat(),
                    "previous_chain_supply": previous_supply_by_chain.get(chain_key, 0.0),
                    "current_chain_supply": current_supply_by_chain.get(chain_key, 0.0),
                    "delta_chain_supply": chain_delta_map[chain_key],
                    "total_positive_delta": total_positive_delta,
                    "total_negative_delta": total_negative_delta,
                    "bridge_amount": bridge_amount,
                    "total_supply_previous": total_supply_previous,
                    "total_supply_current": total_supply_current,
                    "chain_delta_map": chain_delta_map,
                }
                points.append(
                    self._build_point(
                        factor=factor_map["stablecoin_bridge_inflow"],
                        entity_type="stablecoin_chain",
                        entity_key=entity_key,
                        interval="1d",
                        observation_time=observation_time,
                        value=bridge_inflow,
                        quality_flag="ok",
                        dimensions_json=chain_dimensions,
                        source_symbol=chain_source_symbol,
                        raw_payload={
                            **common_payload,
                            "event_type": "bridge_in",
                            "value": bridge_inflow,
                        },
                    )
                )
                points.append(
                    self._build_point(
                        factor=factor_map["stablecoin_bridge_outflow"],
                        entity_type="stablecoin_chain",
                        entity_key=entity_key,
                        interval="1d",
                        observation_time=observation_time,
                        value=bridge_outflow,
                        quality_flag="ok",
                        dimensions_json=chain_dimensions,
                        source_symbol=chain_source_symbol,
                        raw_payload={
                            **common_payload,
                            "event_type": "bridge_out",
                            "value": bridge_outflow,
                        },
                    )
                )

        return points

    def _load_asset_contexts(
        self,
        entity_keys: list[str] | None = None,
    ) -> list[dict[str, object]]:
        tracked_assets = load_stablecoin_assets(entity_keys=entity_keys)
        if not tracked_assets:
            return []

        assets_payload = self.client.fetch_stablecoin_assets()
        contexts: list[dict[str, object]] = []
        for asset_config in tracked_assets:
            asset_payload = self._select_asset_payload(asset_config, assets_payload)
            if asset_payload is None:
                logger.warning(
                    f"稳定币资产未命中上游返回 [{asset_config['entity_key']}]"
                )
                continue

            asset_id = (
                asset_payload.get("id")
                or asset_payload.get("gecko_id")
                or asset_payload.get("slug")
                or asset_config["entity_key"]
            )
            history_rows = self.client.fetch_stablecoin_history(asset_id)
            chain_history_rows = []
            if hasattr(self.client, "fetch_stablecoin_chain_history"):
                try:
                    chain_history_rows = self.client.fetch_stablecoin_chain_history(asset_id)
                except Exception as exc:
                    logger.warning(
                        f"稳定币链级历史获取失败 [{asset_config['entity_key']}] [{asset_id}]: {exc}"
                    )
            current_time = self._to_observation_time(
                asset_payload.get("timestamp")
                or asset_payload.get("date")
                or asset_payload.get("updatedAt")
                or asset_payload.get("lastUpdated"),
                utc_now_naive(),
            )
            current_supply = self._extract_current_supply(asset_payload)
            normalized_history = []
            for row in history_rows:
                timestamp = self._to_observation_time(row.get("timestamp"), current_time)
                supply = AlternativeDataClient._extract_number(row.get("supply"))
                if supply is None:
                    continue
                normalized_history.append(
                    {
                        "timestamp": timestamp,
                        "supply": float(supply),
                    }
                )
            if current_supply is not None:
                normalized_history.append(
                    {
                        "timestamp": current_time,
                        "supply": float(current_supply),
                    }
                )
            deduped_history = {
                item["timestamp"]: item
                for item in normalized_history
            }
            ordered_history = [
                deduped_history[key]
                for key in sorted(deduped_history)
            ]
            normalized_chain_history = self._normalize_chain_history_snapshots(
                chain_history_rows,
                default_time=current_time,
            )
            current_chain_rows = self._extract_chain_supplies(asset_payload)
            if current_chain_rows:
                normalized_chain_history.append(
                    {
                        "timestamp": current_time,
                        "chains": [
                            {
                                "chain": chain_name,
                                "supply": chain_supply,
                            }
                            for chain_name, chain_supply in current_chain_rows
                        ],
                    }
                )
            deduped_chain_history = {
                item["timestamp"]: item
                for item in normalized_chain_history
            }
            ordered_chain_history = [
                deduped_chain_history[key]
                for key in sorted(deduped_chain_history)
            ]
            contexts.append(
                {
                    "asset_config": asset_config,
                    "asset_payload": asset_payload,
                    "asset_id": asset_id,
                    "current_time": current_time,
                    "current_supply": current_supply,
                    "history": ordered_history,
                    "chain_history": ordered_chain_history,
                }
            )
        return contexts

    def _build_current_points(
        self,
        factor_map: dict[str, object],
        context: dict[str, object],
    ) -> list[AlternativeTimeSeriesPoint]:
        asset_config = context["asset_config"]
        asset_payload = context["asset_payload"]
        asset_symbol = str(asset_config["entity_key"])
        asset_id = context["asset_id"]
        observation_time = context["current_time"]
        current_supply = context["current_supply"]
        history = context["history"]
        if current_supply is None:
            return []

        base_dimensions = {
            "aggregation_scope": "asset",
        }
        source_symbol = f"stablecoin:{asset_id}"
        quality_flag = "ok" if history else "fallback"
        baseline_24h = self._find_baseline_record(
            history,
            observation_time - timedelta(days=1),
            tolerance=timedelta(hours=18),
        )
        baseline_7d = self._find_baseline_record(
            history,
            observation_time - timedelta(days=7),
            tolerance=timedelta(days=2),
        )

        points = [
            self._build_point(
                factor=factor_map["stablecoin_total_supply"],
                entity_type="stablecoin_asset",
                entity_key=asset_symbol,
                interval="1h",
                observation_time=observation_time,
                value=current_supply,
                quality_flag=quality_flag,
                dimensions_json=base_dimensions,
                source_symbol=source_symbol,
                raw_payload={
                    "asset_id": asset_id,
                    "asset": asset_symbol,
                    "current_supply": current_supply,
                },
            )
        ]

        if baseline_24h is not None:
            points.append(
                self._build_point(
                    factor=factor_map["stablecoin_net_supply_change_24h"],
                    entity_type="stablecoin_asset",
                    entity_key=asset_symbol,
                    interval="1h",
                    observation_time=observation_time,
                    value=current_supply - baseline_24h["supply"],
                    quality_flag=quality_flag,
                    dimensions_json=base_dimensions,
                    source_symbol=source_symbol,
                    raw_payload={
                        "asset_id": asset_id,
                        "asset": asset_symbol,
                        "current_supply": current_supply,
                        "baseline_timestamp": baseline_24h["timestamp"].isoformat(),
                        "baseline_supply": baseline_24h["supply"],
                    },
                )
            )

        if baseline_7d is not None:
            points.append(
                self._build_point(
                    factor=factor_map["stablecoin_net_supply_change_7d"],
                    entity_type="stablecoin_asset",
                    entity_key=asset_symbol,
                    interval="1h",
                    observation_time=observation_time,
                    value=current_supply - baseline_7d["supply"],
                    quality_flag=quality_flag,
                    dimensions_json=base_dimensions,
                    source_symbol=source_symbol,
                    raw_payload={
                        "asset_id": asset_id,
                        "asset": asset_symbol,
                        "current_supply": current_supply,
                        "baseline_timestamp": baseline_7d["timestamp"].isoformat(),
                        "baseline_supply": baseline_7d["supply"],
                    },
                )
            )

        for chain_name, chain_supply in self._extract_chain_supplies(asset_payload):
            chain_key = self._normalize_chain_key(chain_name)
            chain_dimensions = {
                "aggregation_scope": "asset_chain",
                "asset": asset_symbol,
                "chain": chain_key,
            }
            entity_key = f"{asset_symbol}:{chain_key}"
            chain_source_symbol = f"{source_symbol}:{chain_key}"
            points.append(
                self._build_point(
                    factor=factor_map["stablecoin_chain_supply"],
                    entity_type="stablecoin_chain",
                    entity_key=entity_key,
                    interval="1h",
                    observation_time=observation_time,
                    value=chain_supply,
                    quality_flag=quality_flag,
                    dimensions_json=chain_dimensions,
                    source_symbol=chain_source_symbol,
                    raw_payload={
                        "asset_id": asset_id,
                        "asset": asset_symbol,
                        "chain": chain_name,
                        "chain_supply": chain_supply,
                    },
                )
            )
            if current_supply > 0:
                points.append(
                    self._build_point(
                        factor=factor_map["stablecoin_chain_supply_share"],
                        entity_type="stablecoin_chain",
                        entity_key=entity_key,
                        interval="1h",
                        observation_time=observation_time,
                        value=chain_supply / current_supply,
                        quality_flag=quality_flag,
                        dimensions_json=chain_dimensions,
                        source_symbol=chain_source_symbol,
                        raw_payload={
                            "asset_id": asset_id,
                            "asset": asset_symbol,
                            "chain": chain_name,
                            "chain_supply": chain_supply,
                            "total_supply": current_supply,
                        },
                    )
                )

        points.extend(
            self._build_event_points(
                factor_map=factor_map,
                context=context,
                latest_only=True,
            )
        )
        return points

    def _build_history_points(
        self,
        factor_map: dict[str, object],
        context: dict[str, object],
    ) -> list[AlternativeTimeSeriesPoint]:
        asset_config = context["asset_config"]
        asset_symbol = str(asset_config["entity_key"])
        asset_id = context["asset_id"]
        history = context["history"]
        chain_history = context.get("chain_history") or []
        if not history and not chain_history:
            return []

        base_dimensions = {
            "aggregation_scope": "asset",
        }
        source_symbol = f"stablecoin:{asset_id}"
        points: list[AlternativeTimeSeriesPoint] = []
        for row in history:
            observation_time = row["timestamp"]
            supply = row["supply"]
            points.append(
                self._build_point(
                    factor=factor_map["stablecoin_total_supply"],
                    entity_type="stablecoin_asset",
                    entity_key=asset_symbol,
                    interval="1d",
                    observation_time=observation_time,
                    value=supply,
                    quality_flag="ok",
                    dimensions_json=base_dimensions,
                    source_symbol=source_symbol,
                    raw_payload={
                        "asset_id": asset_id,
                        "asset": asset_symbol,
                        "current_supply": supply,
                    },
                )
            )

            baseline_24h = self._find_baseline_record(
                history,
                observation_time - timedelta(days=1),
                tolerance=timedelta(hours=18),
            )
            if baseline_24h is not None:
                points.append(
                    self._build_point(
                        factor=factor_map["stablecoin_net_supply_change_24h"],
                        entity_type="stablecoin_asset",
                        entity_key=asset_symbol,
                        interval="1d",
                        observation_time=observation_time,
                        value=supply - baseline_24h["supply"],
                        quality_flag="ok",
                        dimensions_json=base_dimensions,
                        source_symbol=source_symbol,
                        raw_payload={
                            "asset_id": asset_id,
                            "asset": asset_symbol,
                            "baseline_timestamp": baseline_24h["timestamp"].isoformat(),
                            "baseline_supply": baseline_24h["supply"],
                        },
                    )
                )

            baseline_7d = self._find_baseline_record(
                history,
                observation_time - timedelta(days=7),
                tolerance=timedelta(days=2),
            )
            if baseline_7d is not None:
                points.append(
                    self._build_point(
                        factor=factor_map["stablecoin_net_supply_change_7d"],
                        entity_type="stablecoin_asset",
                        entity_key=asset_symbol,
                        interval="1d",
                        observation_time=observation_time,
                        value=supply - baseline_7d["supply"],
                        quality_flag="ok",
                        dimensions_json=base_dimensions,
                        source_symbol=source_symbol,
                        raw_payload={
                            "asset_id": asset_id,
                            "asset": asset_symbol,
                            "baseline_timestamp": baseline_7d["timestamp"].isoformat(),
                            "baseline_supply": baseline_7d["supply"],
                        },
                    )
                )

        for snapshot in chain_history:
            observation_time = snapshot["timestamp"]
            asset_total_row = self._find_baseline_record(
                history,
                observation_time,
                tolerance=timedelta(days=2),
            )
            total_supply = (
                asset_total_row["supply"]
                if asset_total_row is not None
                else sum(
                    float(item.get("supply") or 0.0)
                    for item in snapshot.get("chains", [])
                )
            )
            for chain_row in snapshot.get("chains", []):
                chain_name = str(chain_row["chain"])
                chain_key = self._normalize_chain_key(chain_name)
                chain_supply = float(chain_row["supply"])
                chain_dimensions = {
                    "aggregation_scope": "asset_chain",
                    "asset": asset_symbol,
                    "chain": chain_key,
                }
                entity_key = f"{asset_symbol}:{chain_key}"
                chain_source_symbol = f"{source_symbol}:{chain_key}"
                points.append(
                    self._build_point(
                        factor=factor_map["stablecoin_chain_supply"],
                        entity_type="stablecoin_chain",
                        entity_key=entity_key,
                        interval="1d",
                        observation_time=observation_time,
                        value=chain_supply,
                        quality_flag="ok",
                        dimensions_json=chain_dimensions,
                        source_symbol=chain_source_symbol,
                        raw_payload={
                            "asset_id": asset_id,
                            "asset": asset_symbol,
                            "chain": chain_name,
                            "chain_supply": chain_supply,
                            "total_supply": total_supply,
                        },
                    )
                )
                if total_supply > 0:
                    points.append(
                        self._build_point(
                            factor=factor_map["stablecoin_chain_supply_share"],
                            entity_type="stablecoin_chain",
                            entity_key=entity_key,
                            interval="1d",
                            observation_time=observation_time,
                            value=chain_supply / total_supply,
                            quality_flag="ok",
                            dimensions_json=chain_dimensions,
                            source_symbol=chain_source_symbol,
                            raw_payload={
                                "asset_id": asset_id,
                                "asset": asset_symbol,
                                "chain": chain_name,
                                "chain_supply": chain_supply,
                                "total_supply": total_supply,
                            },
                        )
                    )

        points.extend(
            self._build_event_points(
                factor_map=factor_map,
                context=context,
                latest_only=False,
            )
        )
        return points

    def fetch_recent_points(
        self,
        entity_keys: list[str] | None = None,
    ) -> list[AlternativeTimeSeriesPoint]:
        factor_map = {
            factor.factor_id: factor
            for factor in load_alternative_factors(source_names=["stablecoin"])
        }
        results: list[AlternativeTimeSeriesPoint] = []
        for context in self._load_asset_contexts(entity_keys=entity_keys):
            results.extend(self._build_current_points(factor_map, context))
        return results

    def bootstrap_history(
        self,
        entity_keys: list[str] | None = None,
    ) -> list[AlternativeTimeSeriesPoint]:
        factor_map = {
            factor.factor_id: factor
            for factor in load_alternative_factors(source_names=["stablecoin"])
        }
        results: list[AlternativeTimeSeriesPoint] = []
        for context in self._load_asset_contexts(entity_keys=entity_keys):
            results.extend(self._build_history_points(factor_map, context))
            results.extend(self._build_current_points(factor_map, context))
        return results

    def collect(
        self,
        entity_keys: list[str] | None = None,
    ) -> list[AlternativeTimeSeriesPoint]:
        logger.info("开始采集稳定币供给与链分布...")
        points = self.fetch_recent_points(entity_keys=entity_keys)
        if points:
            self.save_to_db(points)
        logger.info(f"稳定币供给与链分布采集完成，共 {len(points)} 条")
        return points
