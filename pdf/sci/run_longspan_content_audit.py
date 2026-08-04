#!/usr/bin/env python3
"""Long-span joint content-proxy audit: macro + stablecoin-flow over 2017-2026.

The PIT archive identifies band content on ~400 days only. This audit extends
the *content* margin to the full 2017+ window using:

  - Yahoo VIX (^VIX) and DXY (DX-Y.NYB) daily closes → macro_tilt
  - DefiLlama aggregate stablecoin circulating USD → alt_tilt
    (sign of 7d supply change, lag-1; proxy for vintaged
    ``stablecoin_net_supply_change_7d``)

Disclosure: Yahoo closes are not vintaged ``available_at`` series; DefiLlama
charts are revised end-of-day aggregates without vintage stamps. Both series
are lagged by one day. This is an external-validity audit of the *joint*
content channel, not a substitute for the PIT vintage construction.

Outputs:
  pdf/data/macro_longspan_yahoo.csv
  pdf/data/stablecoin_longspan_defillama.csv
  pdf/tables/table_longspan_content_summary.csv
  pdf/tables/table_longspan_content_by_year.csv
  pdf/tables/table_longspan_content_bootstrap.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import importlib.util

_jf_path = Path(__file__).resolve().parent / "run_jf_experiments.py"
_spec = importlib.util.spec_from_file_location("run_jf_experiments", _jf_path)
_jf = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_jf)

directional_signal = _jf.directional_signal
bootstrap_delta_pvalues = _jf.bootstrap_delta_pvalues

_ls_path = Path(__file__).resolve().parent / "run_longspan_backtest.py"
_spec2 = importlib.util.spec_from_file_location("run_longspan_backtest", _ls_path)
_ls = importlib.util.module_from_spec(_spec2)
assert _spec2.loader is not None
_spec2.loader.exec_module(_ls)

fetch_yahoo = _ls.fetch_yahoo
policy_daily = _ls.policy_daily
ann_stats = _ls.ann_stats

DATA = Path(__file__).resolve().parents[1] / "data"
TAB = Path(__file__).resolve().parents[1] / "tables"

MACRO_SYMBOLS = {"vix": "^VIX", "dxy": "DX-Y.NYB"}
START = "2016-11-01"  # warmup before 2017 sample
DEFILLAMA_CHART = "https://stablecoins.llama.fi/stablecoincharts/all"


def load_macro_proxy() -> pd.DataFrame:
    cache = DATA / "macro_longspan_yahoo.csv"
    if cache.exists():
        return pd.read_csv(cache, parse_dates=["date"])
    frames = {}
    for name, symbol in MACRO_SYMBOLS.items():
        px = fetch_yahoo(symbol, START)
        frames[name] = px.set_index("date")["close"].rename(name)
    df = pd.concat(frames.values(), axis=1).sort_index()
    # forward-fill weekends/holidays so crypto 7d calendar aligns
    full = pd.date_range(df.index.min(), df.index.max(), freq="D")
    df = df.reindex(full).ffill()
    df.index.name = "date"
    out = df.reset_index()
    out.to_csv(cache, index=False)
    return out


def load_stablecoin_proxy(*, force_refresh: bool = False) -> pd.DataFrame:
    """DefiLlama aggregate peggedUSD circulating → daily series + 7d change."""
    cache = DATA / "stablecoin_longspan_defillama.csv"
    if cache.exists() and not force_refresh:
        return pd.read_csv(cache, parse_dates=["date"])

    import httpx

    with httpx.Client(timeout=120, follow_redirects=True) as client:
        resp = client.get(DEFILLAMA_CHART)
        resp.raise_for_status()
        payload = resp.json()
    if not isinstance(payload, list) or not payload:
        raise SystemExit("DefiLlama stablecoincharts/all returned empty payload")

    rows = []
    for entry in payload:
        ts = entry.get("date")
        circ = (entry.get("totalCirculatingUSD") or {}).get("peggedUSD")
        if ts is None or circ is None:
            continue
        rows.append(
            {
                "date": pd.to_datetime(int(ts), unit="s", utc=True).tz_localize(None).normalize(),
                "stablecoin_circ_usd": float(circ),
            }
        )
    df = pd.DataFrame(rows).drop_duplicates("date").sort_values("date")
    # Fill calendar gaps (DefiLlama is daily but crypto calendars are continuous)
    full = pd.date_range(df["date"].min(), df["date"].max(), freq="D")
    s = df.set_index("date")["stablecoin_circ_usd"].reindex(full).ffill()
    out = s.rename("stablecoin_circ_usd").to_frame()
    out["ssc7"] = out["stablecoin_circ_usd"].diff(7)
    out.index.name = "date"
    out = out.reset_index()
    out.to_csv(cache, index=False)
    return out


def build_macro_tilts(macro: pd.DataFrame) -> pd.DataFrame:
    m = macro.set_index("date").sort_index()
    vix_chg = m["vix"].diff(5).shift(1)  # information strictly before payoff day
    dxy_chg = m["dxy"].diff(5).shift(1)
    tilt = np.where(
        (vix_chg < 0) & (dxy_chg < 0), 1.0, np.where((vix_chg > 0) & (dxy_chg > 0), -1.0, 0.0)
    )
    return pd.DataFrame(
        {
            "date": m.index,
            "macro_tilt": tilt,
            "vix_chg5": vix_chg.to_numpy(),
            "dxy_chg5": dxy_chg.to_numpy(),
        }
    ).dropna(subset=["vix_chg5", "dxy_chg5"])


# Backward-compatible alias used by tests
build_content_tilts = build_macro_tilts


def build_alt_tilts(stable: pd.DataFrame) -> pd.DataFrame:
    """alt_tilt = sign(7d supply change), lag-1 — matches PIT band_content_features."""
    s = stable.set_index("date").sort_index()
    ssc_prev = s["ssc7"].shift(1)
    alt = np.sign(ssc_prev.fillna(0.0))
    return pd.DataFrame(
        {
            "date": s.index,
            "alt_tilt": alt.to_numpy(),
            "ssc7_prev": ssc_prev.to_numpy(),
            "alt_tilt_source": "defillama_stablecoincharts_all",
        }
    ).dropna(subset=["ssc7_prev"])


def build_joint_content_tilts(macro: pd.DataFrame, stable: pd.DataFrame) -> pd.DataFrame:
    m = build_macro_tilts(macro)
    a = build_alt_tilts(stable)
    joint = m.merge(a[["date", "alt_tilt", "ssc7_prev", "alt_tilt_source"]], on="date", how="inner")
    return joint


def inject_content(panel: pd.DataFrame, tilts: pd.DataFrame) -> pd.DataFrame:
    cols = ["date", "macro_tilt"]
    if "alt_tilt" in tilts.columns:
        cols.append("alt_tilt")
    out = panel.merge(tilts[cols], on="date", how="left")
    out["macro_tilt"] = out["macro_tilt"].fillna(0.0)
    out["alt_tilt"] = out["alt_tilt"].fillna(0.0) if "alt_tilt" in out.columns else 0.0
    new_sig = []
    for _, r in out.iterrows():
        eng = {
            "detected_regime": r["detected_regime"],
            "cascade_p": float(r["cascade_p"]),
            "mom5": float(r["mom5"]),
            "macro_tilt": float(r["macro_tilt"]),
            "alt_tilt": float(r["alt_tilt"]),
        }
        new_sig.append(directional_signal(eng))
    out["signal"] = new_sig
    return out


def main() -> int:
    panel_cache = DATA / "longspan_mechanism_panel.csv"
    if not panel_cache.exists():
        raise SystemExit("Run run_longspan_backtest.py first (needs longspan_mechanism_panel.csv)")
    panel = pd.read_csv(panel_cache, parse_dates=["date"])

    macro = load_macro_proxy()
    print("macro proxy", macro["date"].min().date(), "→", macro["date"].max().date(), len(macro))
    stable = load_stablecoin_proxy()
    print(
        "stablecoin proxy",
        stable["date"].min().date(),
        "→",
        stable["date"].max().date(),
        len(stable),
    )

    tilts = build_joint_content_tilts(macro, stable)
    print(
        "joint tilt days",
        len(tilts),
        "macro+ share",
        round(float((tilts["macro_tilt"] > 0).mean()), 3),
        "alt+ share",
        round(float((tilts["alt_tilt"] > 0).mean()), 3),
        "both+ share",
        round(float(((tilts["macro_tilt"] > 0) & (tilts["alt_tilt"] > 0)).mean()), 3),
    )

    with_content = inject_content(panel, tilts)
    n_changed = int((with_content["signal"].to_numpy() != panel["signal"].to_numpy()).sum())
    both_on = int(((with_content["macro_tilt"] > 0) & (with_content["alt_tilt"] > 0)).sum())
    print("signals changed by joint content:", n_changed, "of", len(panel), "; both-tilt-on rows:", both_on)

    # Macro-only arm (ablation): confirms two-band conjunction is structural
    macro_only = inject_content(panel, tilts.assign(alt_tilt=0.0))
    n_macro_only = int((macro_only["signal"].to_numpy() != panel["signal"].to_numpy()).sum())
    print("signals changed by macro-only ablation:", n_macro_only, "of", len(panel))

    curves = {
        "mechanism+joint_content": policy_daily(with_content, "mechanism"),
        "mechanism+macro_only": policy_daily(macro_only, "mechanism"),
        "mechanism (no content)": policy_daily(panel, "mechanism"),
        "momentum": policy_daily(panel, "momentum"),
        "always_long": policy_daily(panel, "always_long"),
    }
    summary = pd.DataFrame([{"policy": k, **ann_stats(v)} for k, v in curves.items()])
    summary.to_csv(TAB / "table_longspan_content_summary.csv", index=False)
    print(summary.to_string(index=False))

    boots = {}
    for name, a, b in [
        ("joint_minus_nocontent", "mechanism+joint_content", "mechanism (no content)"),
        ("joint_minus_momentum", "mechanism+joint_content", "momentum"),
        ("joint_minus_macro_only", "mechanism+joint_content", "mechanism+macro_only"),
        ("macro_only_minus_nocontent", "mechanism+macro_only", "mechanism (no content)"),
        ("nocontent_minus_momentum", "mechanism (no content)", "momentum"),
        # Keep legacy keys for manuscript/table consumers
        ("content_minus_nocontent", "mechanism+joint_content", "mechanism (no content)"),
        ("content_minus_momentum", "mechanism+joint_content", "momentum"),
    ]:
        for method in ("circular", "stationary"):
            boots[f"{name}_{method}"] = bootstrap_delta_pvalues(
                curves[a], curves[b], n_boot=999, block=5, method=method
            )
    (TAB / "table_longspan_content_bootstrap.json").write_text(
        json.dumps(
            {
                "disclosure": (
                    "Yahoo VIX/DXY closes (same-evening) + DefiLlama aggregate "
                    "stablecoin circulating USD 7d change; both one-day lagged; "
                    "joint-content proxy for vintaged PIT macro/alternative bands."
                ),
                "n_signals_changed": n_changed,
                "n_signals_changed_macro_only": n_macro_only,
                "n_both_tilt_on": both_on,
                "alt_source": "defillama_stablecoincharts_all",
                **boots,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    for k, v in boots.items():
        if k.endswith("_circular"):
            print(k, {kk: v[kk] for kk in ("n_days", "method", "dCE", "p_CE", "ci_dCE_05", "ci_dCE_95")})

    with_content["year"] = with_content["date"].dt.year
    panel["year"] = panel["date"].dt.year
    rows = []
    for y in sorted(with_content["year"].unique()):
        gc = with_content[with_content["year"] == y]
        gp = panel[panel["year"] == y]
        cur_c = policy_daily(gc, "mechanism")
        cur_p = policy_daily(gp, "mechanism")
        cur_m = policy_daily(gp, "momentum")
        rows.append(
            {
                "year": int(y),
                "n_days": int(gc["date"].nunique()),
                "content_ann_ret": ann_stats(cur_c)["ann_return"],
                "content_Sharpe": ann_stats(cur_c)["Sharpe"],
                "nocontent_ann_ret": ann_stats(cur_p)["ann_return"],
                "nocontent_Sharpe": ann_stats(cur_p)["Sharpe"],
                "momentum_Sharpe": ann_stats(cur_m)["Sharpe"],
                "tilt_active_share": round(
                    float(((gc["macro_tilt"] != 0) | (gc["alt_tilt"] != 0)).mean()), 3
                ),
                "both_tilt_on_share": round(
                    float(((gc["macro_tilt"] > 0) & (gc["alt_tilt"] > 0)).mean()), 3
                ),
            }
        )
    by_year = pd.DataFrame(rows)
    by_year.to_csv(TAB / "table_longspan_content_by_year.csv", index=False)
    print(by_year.to_string(index=False))
    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
