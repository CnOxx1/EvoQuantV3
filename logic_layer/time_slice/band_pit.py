"""Multi-band point-in-time readiness from raw history tables.

Complements snapshot-based TimeSliceService: when analytics snapshots are sparse,
band readiness at time t can still be reconstructed from exchange/market history.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from logic_layer.asset_readiness.service import AssetReadinessService

# Daily-scale freshness thresholds (seconds)
BAND_FRESH_SECONDS: dict[str, int] = {
    "exchange": 2 * 86400,
    "macro": 5 * 86400,
    "news": 3 * 86400,
    "onchain": 3 * 86400,
    "options": 3 * 86400,
    "tokenomics": 7 * 86400,
    "alternative": 7 * 86400,
    "event_calendar": 14 * 86400,
}


@dataclass
class BandObservation:
    band: str
    status: str  # ready | limited | missing
    observation_time: str | None
    age_seconds: float | None


def _parse_ts(ts: str | datetime) -> datetime:
    if isinstance(ts, datetime):
        return ts.replace(tzinfo=None)
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%d"):
        try:
            return datetime.strptime(ts, fmt)
        except ValueError:
            continue
    raise ValueError(f"cannot parse timestamp: {ts}")


def _iso(ts: str | datetime) -> str:
    if isinstance(ts, datetime):
        return ts.strftime("%Y-%m-%dT%H:%M:%S")
    return str(ts)


def _table_exists(conn, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return bool(row)


def _latest(conn, sql: str, params: tuple) -> str | None:
    try:
        row = conn.execute(sql, params).fetchone()
    except Exception:
        return None
    if not row or row[0] is None:
        return None
    return str(row[0])


def _status_from_age(age_seconds: float | None, fresh_seconds: int) -> str:
    if age_seconds is None:
        return "missing"
    if age_seconds <= fresh_seconds:
        return "ready"
    if age_seconds <= fresh_seconds * 3:
        return "limited"
    return "missing"


class BandPITService:
    """Reconstruct evidence-band readiness at an arbitrary timestamp."""

    def __init__(self):
        from database.router import DatabaseRouter, Domain

        self.router = DatabaseRouter()
        self.exchange = self.router.get_manager(Domain.EXCHANGE_DATA)
        self.market = self.router.get_manager(Domain.MARKET_DATA)
        self.analytics = self.router.get_analytics_db()

    def latest_band_time(self, band: str, asof: str | datetime, symbol: str | None = None) -> str | None:
        asof_s = _iso(asof)
        ex, mk, an = self.exchange.conn, self.market.conn, self.analytics.conn
        symbol = symbol or "BTC/USDT"

        if band == "exchange":
            # Prefer the freshest bar <= asof across merged and raw klines so an
            # incomplete merged archive cannot hide longer exchange history.
            candidates: list[str] = []
            if _table_exists(an, "merged_klines"):
                ts = _latest(
                    an,
                    """SELECT MAX(open_time) FROM merged_klines
                       WHERE symbol=? AND timeframe='1d' AND open_time<=?""",
                    (symbol, asof_s),
                )
                if ts:
                    candidates.append(ts)
            if _table_exists(ex, "klines"):
                ts = _latest(
                    ex,
                    """SELECT MAX(open_time) FROM klines
                       WHERE symbol=? AND timeframe='1d' AND open_time<=?""",
                    (symbol, asof_s),
                )
                if ts:
                    candidates.append(ts)
            return max(candidates) if candidates else None

        if band == "macro" and _table_exists(mk, "macro_timeseries"):
            cols = [r[1] for r in mk.execute("PRAGMA table_info(macro_timeseries)").fetchall()]
            if "available_at" in cols:
                return _latest(
                    mk,
                    """SELECT MAX(COALESCE(available_at, observation_time))
                       FROM macro_timeseries
                       WHERE COALESCE(available_at, observation_time) <= ?""",
                    (asof_s,),
                )
            return _latest(
                mk,
                "SELECT MAX(observation_time) FROM macro_timeseries WHERE observation_time<=?",
                (asof_s,),
            )

        mapping = {
            "onchain": ("onchain_timeseries", "observation_time"),
            "options": ("options_timeseries", "observation_time"),
            "tokenomics": ("tokenomics_timeseries", "observation_time"),
            "alternative": ("alternative_timeseries", "observation_time"),
        }
        if band in mapping and _table_exists(mk, mapping[band][0]):
            table, col = mapping[band]
            return _latest(mk, f"SELECT MAX({col}) FROM {table} WHERE {col}<=?", (asof_s,))

        if band == "news" and _table_exists(mk, "news_articles"):
            cols = [r[1] for r in mk.execute("PRAGMA table_info(news_articles)").fetchall()]
            tcol = "published_at" if "published_at" in cols else ("collected_at" if "collected_at" in cols else None)
            if tcol:
                return _latest(mk, f"SELECT MAX({tcol}) FROM news_articles WHERE {tcol}<=?", (asof_s,))

        if band == "event_calendar" and _table_exists(mk, "event_calendar_events"):
            cols = [r[1] for r in mk.execute("PRAGMA table_info(event_calendar_events)").fetchall()]
            tcol = "event_time" if "event_time" in cols else ("collected_at" if "collected_at" in cols else None)
            if tcol:
                return _latest(mk, f"SELECT MAX({tcol}) FROM event_calendar_events WHERE {tcol}<=?", (asof_s,))
        return None

    def observe_band(self, band: str, asof: str | datetime, symbol: str | None = None) -> BandObservation:
        asof_dt = _parse_ts(asof)
        obs = self.latest_band_time(band, asof, symbol=symbol)
        if not obs:
            return BandObservation(band=band, status="missing", observation_time=None, age_seconds=None)
        age = (asof_dt - _parse_ts(obs)).total_seconds()
        status = _status_from_age(age, BAND_FRESH_SECONDS.get(band, 3 * 86400))
        return BandObservation(band=band, status=status, observation_time=obs, age_seconds=age)

    def get_band_readiness_at(
        self,
        timestamp: str | datetime,
        symbols: list[str] | None = None,
    ) -> dict[str, Any]:
        """Return market + per-asset band readiness reconstructed at timestamp."""
        asof = _iso(timestamp)
        bands = list(AssetReadinessService.BAND_WEIGHTS.keys())
        market = {b: self.observe_band(b, asof).status for b in bands if b != "exchange"}
        # market-level exchange uses BTC as anchor when present
        market["exchange"] = self.observe_band("exchange", asof, symbol="BTC/USDT").status

        assets_out = []
        for sym in symbols or ["BTC/USDT"]:
            statuses = dict(market)
            statuses["exchange"] = self.observe_band("exchange", asof, symbol=sym).status
            score = 0.0
            for b, w in AssetReadinessService.BAND_WEIGHTS.items():
                score += w * AssetReadinessService._status_ratio(statuses.get(b, "missing"))
            ready_n = sum(1 for s in statuses.values() if s == "ready")
            limited_n = sum(1 for s in statuses.values() if s == "limited")
            assets_out.append(
                {
                    "symbol": sym,
                    "band_statuses": statuses,
                    "readiness_score": round(score, 4),
                    "n_ready": ready_n,
                    "n_limited": limited_n,
                }
            )

        mean_score = round(sum(a["readiness_score"] for a in assets_out) / max(len(assets_out), 1), 4)
        return {
            "as_of": asof,
            "source": "raw_history_band_pit",
            "market_band_statuses": market,
            "assets": assets_out,
            "average_readiness_score": mean_score,
            "band_fresh_seconds": dict(BAND_FRESH_SECONDS),
        }
