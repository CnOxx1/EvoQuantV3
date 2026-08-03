#!/usr/bin/env python3
"""Build a multi-band point-in-time archive from populated SQLite history tables.

For each calendar day t and paper asset:
- query each band's history for latest observation_time <= t
- mark band fresh/stale/missing from age thresholds
- compute readiness / WMI / ACWMI using production code
- attach next-day (or same-day close-to-close) Yahoo returns for economic value
- detect availability shocks when a previously-fresh band becomes stale/missing

Output: pdf/data/pit_multiband_panel.csv and summary JSON.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from logic_layer.ai_market_context.service import AIMarketContextService
from logic_layer.asset_readiness.service import AssetReadinessService
from logic_layer.time_slice.band_pit import BAND_FRESH_SECONDS, BandPITService

DATA = Path(__file__).resolve().parents[1] / "data"
DATA.mkdir(parents=True, exist_ok=True)

PAPER_ASSETS = ["BTC", "ETH", "SOL", "XRP", "BNB", "ADA", "AVAX", "LINK", "DOT", "NEAR"]
ASSET_TO_SYMBOL = {
    "BTC": "BTC/USDT",
    "ETH": "ETH/USDT",
    "SOL": "SOL/USDT",
    "XRP": "XRP/USDT",
    "BNB": "BNB/USDT",
    "ADA": "ADA/USDT",
    "AVAX": "AVAX/USDT",
    "LINK": "LINK/USDT",
    "DOT": "DOT/USDT",
    "NEAR": "NEAR/USDT",
}

# age thresholds (days) — keep aligned with production BandPITService seconds
FRESH_DAYS = {k: max(1, int(v / 86400)) for k, v in BAND_FRESH_SECONDS.items()}

REGIME_GAMMA = {
    "trend": (1.0, 1.0, 1.0, 1.3, 0.8),
    "range": (1.0, 1.1, 1.1, 1.0, 1.0),
    "crisis": (0.9, 1.2, 1.4, 0.8, 1.5),
}


def connect_dbs():
    from database.router import DatabaseRouter, Domain

    r = DatabaseRouter()
    return {
        "exchange": r.get_manager(Domain.EXCHANGE_DATA).conn,
        "market": r.get_manager(Domain.MARKET_DATA).conn,
        "analytics": r.get_analytics_db().conn,
    }


def table_exists(conn, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def latest_ts(conn, sql: str, params: tuple) -> pd.Timestamp | None:
    try:
        row = conn.execute(sql, params).fetchone()
    except Exception:
        return None
    if not row or row[0] is None:
        return None
    return pd.to_datetime(row[0], utc=False, errors="coerce")


def band_observation_time(
    conns,
    band: str,
    symbol: str,
    asof: pd.Timestamp,
    pit: BandPITService | None = None,
) -> pd.Timestamp | None:
    """Return latest observation time <= asof for a band.

    Prefers production ``BandPITService`` so paper panels and live time-slice
    share one reconstruction path.
    """
    asof_s = asof.strftime("%Y-%m-%dT%H:%M:%S")
    if pit is not None:
        raw = pit.latest_band_time(band, asof_s, symbol=symbol)
        if raw:
            ts = pd.to_datetime(raw, utc=False, errors="coerce")
            if ts is not None and not pd.isna(ts):
                return ts

    # Fallback SQL (kept for offline/tests without full router wiring)
    ex, mk, an = conns["exchange"], conns["market"], conns["analytics"]

    if band == "exchange":
        # prefer merged_klines 1d, else raw klines
        if table_exists(an, "merged_klines"):
            ts = latest_ts(
                an,
                """
                SELECT MAX(open_time) FROM merged_klines
                WHERE symbol=? AND timeframe='1d' AND open_time<=?
                """,
                (symbol, asof_s),
            )
            if ts is not None and not pd.isna(ts):
                return ts
        if table_exists(ex, "klines"):
            return latest_ts(
                ex,
                """
                SELECT MAX(open_time) FROM klines
                WHERE symbol=? AND timeframe='1d' AND open_time<=?
                """,
                (symbol, asof_s),
            )
        return None

    if band == "macro" and table_exists(mk, "macro_timeseries"):
        # use available_at when present for true PIT, else observation_time
        cols = [r[1] for r in mk.execute("PRAGMA table_info(macro_timeseries)").fetchall()]
        if "available_at" in cols:
            return latest_ts(
                mk,
                """
                SELECT MAX(COALESCE(available_at, observation_time)) FROM macro_timeseries
                WHERE COALESCE(available_at, observation_time) <= ?
                """,
                (asof_s,),
            )
        return latest_ts(
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
    if band in mapping and table_exists(mk, mapping[band][0]):
        table, col = mapping[band]
        return latest_ts(mk, f"SELECT MAX({col}) FROM {table} WHERE {col}<=?", (asof_s,))

    if band == "news" and table_exists(mk, "news_articles"):
        cols = [r[1] for r in mk.execute("PRAGMA table_info(news_articles)").fetchall()]
        tcol = "published_at" if "published_at" in cols else ("collected_at" if "collected_at" in cols else None)
        if tcol:
            return latest_ts(mk, f"SELECT MAX({tcol}) FROM news_articles WHERE {tcol}<=?", (asof_s,))

    if band == "event_calendar" and table_exists(mk, "event_calendar_events"):
        cols = [r[1] for r in mk.execute("PRAGMA table_info(event_calendar_events)").fetchall()]
        tcol = "event_time" if "event_time" in cols else ("collected_at" if "collected_at" in cols else None)
        if tcol:
            return latest_ts(
                mk,
                f"SELECT MAX({tcol}) FROM event_calendar_events WHERE {tcol}<=?",
                (asof_s,),
            )

    # funding contributes to exchange-band richness via separate age field in panel builder
    return None


def status_from_age(age_days: float | None, fresh_days: float) -> str:
    if age_days is None or not np.isfinite(age_days):
        return "missing"
    if age_days <= fresh_days:
        return "ready"
    if age_days <= fresh_days * 3:
        return "limited"
    return "missing"


def readiness_ratio(status: str) -> float:
    return float(AssetReadinessService._status_ratio(status))


def continuous_honesty(excl_rate: float, cont_rate: float) -> float:
    return float(np.exp(-2.0 * cont_rate) * max(0.0, 1.0 - 0.5 * (1.0 - excl_rate)))


def acwmi(B, U, H, S, C, gamma) -> float:
    vals = np.array([max(B, 1e-6), max(U, 1e-6), max(H, 1e-6), max(S, 1e-6), max(C, 1e-6)])
    g = np.array(gamma, dtype=float)
    return float(np.exp(np.sum(g * np.log(vals)) / np.sum(g)))


def build_panel() -> pd.DataFrame:
    returns = pd.read_csv(DATA / "crypto_daily_yahoo.csv", parse_dates=["date"])
    returns = returns.dropna(subset=["ret"])
    returns = returns[returns["asset"].isin(PAPER_ASSETS)].copy()
    conns = connect_dbs()
    pit = BandPITService()

    # date range: intersection of returns and any exchange history
    dates = sorted(returns["date"].unique())
    # trim to period with some exchange coverage if available
    sample_symbol = "BTC/USDT"
    first_ex = band_observation_time(
        conns, "exchange", sample_symbol, pd.Timestamp(dates[-1]), pit=pit
    )
    # find earliest exchange bar
    an = conns["analytics"]
    ex = conns["exchange"]
    earliest = None
    if table_exists(an, "merged_klines"):
        row = an.execute(
            "SELECT MIN(open_time) FROM merged_klines WHERE symbol=? AND timeframe='1d'",
            (sample_symbol,),
        ).fetchone()
        if row and row[0]:
            earliest = pd.to_datetime(row[0])
    if earliest is None and table_exists(ex, "klines"):
        row = ex.execute(
            "SELECT MIN(open_time) FROM klines WHERE symbol=? AND timeframe='1d'",
            (sample_symbol,),
        ).fetchone()
        if row and row[0]:
            earliest = pd.to_datetime(row[0])
    if earliest is not None:
        dates = [d for d in dates if pd.Timestamp(d) >= earliest]
    print("PIT dates", dates[0] if dates else None, "→", dates[-1] if dates else None, "n=", len(dates))
    print("first_ex_asof_end", first_ex)

    bands = list(AssetReadinessService.BAND_WEIGHTS.keys())
    rows = []
    prev_status = {b: "missing" for b in bands}
    # Bands with durable history in this archive (used for shock identification)
    shock_eligible = {"exchange", "macro", "alternative"}

    for d in dates:
        asof = pd.Timestamp(d) + pd.Timedelta(hours=23, minutes=59)
        # band statuses are market-level for non-exchange; exchange can be asset-specific
        market_status = {}
        market_age = {}
        for b in bands:
            if b == "exchange":
                continue
            ts = band_observation_time(conns, b, sample_symbol, asof, pit=pit)
            age = (asof - ts).total_seconds() / 86400.0 if ts is not None and not pd.isna(ts) else None
            st = status_from_age(age, FRESH_DAYS.get(b, 3))
            market_status[b] = st
            market_age[b] = age

        # BTC exchange status anchors market-level exchange availability shock
        ts_btc = band_observation_time(conns, "exchange", "BTC/USDT", asof, pit=pit)
        age_btc = (asof - ts_btc).total_seconds() / 86400.0 if ts_btc is not None and not pd.isna(ts_btc) else None
        st_btc = status_from_age(age_btc, FRESH_DAYS["exchange"])
        market_status["exchange"] = st_btc
        market_age["exchange"] = age_btc

        shock_bands = []
        for b in shock_eligible:
            st = market_status.get(b, "missing")
            if prev_status.get(b) == "ready" and st in {"missing", "limited"}:
                shock_bands.append(b)
        market_outage = int(len(shock_bands) > 0)
        macro_age = market_age.get("macro")

        day_rets = returns[returns["date"] == d]
        for _, r in day_rets.iterrows():
            asset = r["asset"]
            symbol = ASSET_TO_SYMBOL.get(asset)
            if not symbol:
                continue
            # exchange status asset-specific
            ts_ex = band_observation_time(conns, "exchange", symbol, asof, pit=pit)
            age_ex = (asof - ts_ex).total_seconds() / 86400.0 if ts_ex is not None and not pd.isna(ts_ex) else None
            st_ex = status_from_age(age_ex, FRESH_DAYS["exchange"])
            statuses = dict(market_status)
            statuses["exchange"] = st_ex

            # hierarchical breadth via production weights
            B_asset = 0.0
            for b, w in AssetReadinessService.BAND_WEIGHTS.items():
                B_asset += w * readiness_ratio(statuses.get(b, "missing"))
            req = [readiness_ratio(statuses.get(b, "missing")) for b in AssetReadinessService.REQUIRED_BANDS]
            B_band = float(np.mean(req)) if req else B_asset
            B_domain = float(np.mean([readiness_ratio(statuses[b]) for b in statuses]))
            B_hier = 0.25 * B_domain + 0.35 * B_band + 0.40 * B_asset

            ready_n = sum(1 for s in statuses.values() if s == "ready")
            limited_n = sum(1 for s in statuses.values() if s == "limited")
            missing_n = sum(1 for s in statuses.values() if s == "missing")
            total = max(len(statuses), 1)
            U = (ready_n + 0.7 * limited_n) / total
            excl = ready_n / total  # share kept as main-view ready
            cont = limited_n / total * 0.5  # limited treated as partial contamination risk
            H = continuous_honesty(excl, cont)
            flag = "ok" if B_hier >= 0.55 and cont < 0.15 else ("thin" if B_hier >= 0.35 else "blocked")
            fresh = ready_n
            acceptable = limited_n
            # S/C placeholders for world-only panel; engines refine on returns later.
            # Use production ACWMI path so index_mode / thresholds stay paper-aligned.
            S = 0.5
            C = 0.5
            wmi_payload = AIMarketContextService._compute_world_model_index(
                coverage_score=float(B_hier),
                pipeline_latency_context={"summary": {"total_domains": total, "fresh": fresh, "acceptable": acceptable}},
                data_quality_flag=flag,
                data_quality_flags=[],
                signal_integrity=S,
                cross_evidence=C,
                gamma=REGIME_GAMMA["range"],
                index_mode="acwmi",
            )
            wmi = wmi_payload["wmi"]
            gamma = REGIME_GAMMA["range"]
            ac = float(wmi_payload.get("acwmi") or acwmi(B_hier, U, H, S, C, gamma))

            # Asset-level availability shock: exchange not ready, or market band transition.
            asset_shock = int(st_ex in {"missing", "limited"} or market_outage == 1)
            row = {
                "date": d,
                "asset": asset,
                "symbol": symbol,
                "ret": float(r["ret"]),
                "B_hier": B_hier,
                "U": U,
                "H_cont": H,
                "WMI": wmi,
                "ACWMI_world": ac,  # world-only; engines overwrite S/C later
                "outage": asset_shock,
                "market_outage": market_outage,
                "shock_bands": "|".join(shock_bands + (["exchange"] if st_ex != "ready" else [])),
                "macro_age": macro_age,
                "n_ready": ready_n,
                "n_limited": limited_n,
                "n_missing": missing_n,
            }
            for b in bands:
                row[f"st_{b}"] = statuses.get(b, "missing")
                row[f"age_{b}"] = age_ex if b == "exchange" else market_age.get(b)
            rows.append(row)

        prev_status = dict(market_status)

    df = pd.DataFrame(rows)
    out = DATA / "pit_multiband_panel.csv"
    df.to_csv(out, index=False)
    summary = {
        "n_rows": int(len(df)),
        "n_days": int(df["date"].nunique()) if len(df) else 0,
        "start": str(pd.Timestamp(df["date"].min()).date()) if len(df) else None,
        "end": str(pd.Timestamp(df["date"].max()).date()) if len(df) else None,
        "mean_ready": float(df["n_ready"].mean()) if len(df) else 0,
        "outage_rate": float(df["outage"].mean()) if len(df) else 0,
        "band_ready_rates": {
            b: float((df[f"st_{b}"] == "ready").mean()) for b in bands if f"st_{b}" in df.columns
        },
    }
    (DATA / "pit_archive_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print("Wrote", out)
    return df


if __name__ == "__main__":
    build_panel()
