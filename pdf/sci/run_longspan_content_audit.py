#!/usr/bin/env python3
"""Long-span content-proxy audit: macro_tilt over 2017-2026 BTC/ETH.

The PIT archive identifies band content on ~400 days only. This audit extends
the *content* margin to the full 2017+ window using Yahoo VIX (^VIX) and DXY
(DX-Y.NYB) daily closes as a macro-content proxy.

Disclosure: Yahoo closes are not vintaged `available_at` series. VIX/DXY are
published same-evening with negligible revision, so the proxy is timing-safe at
the daily horizon (we additionally lag by one day), but this is an
external-validity audit of the content channel, not a substitute for the PIT
vintage construction.

Outputs:
  pdf/data/macro_longspan_yahoo.csv            cached VIX/DXY closes
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


def build_content_tilts(macro: pd.DataFrame) -> pd.DataFrame:
    m = macro.set_index("date").sort_index()
    vix_chg = m["vix"].diff(5).shift(1)  # information strictly before payoff day
    dxy_chg = m["dxy"].diff(5).shift(1)
    tilt = np.where(
        (vix_chg < 0) & (dxy_chg < 0), 1.0, np.where((vix_chg > 0) & (dxy_chg > 0), -1.0, 0.0)
    )
    return pd.DataFrame({"date": m.index, "macro_tilt": tilt, "vix_chg5": vix_chg.to_numpy(), "dxy_chg5": dxy_chg.to_numpy()}).dropna(subset=["vix_chg5", "dxy_chg5"])


def inject_content(panel: pd.DataFrame, tilts: pd.DataFrame) -> pd.DataFrame:
    out = panel.merge(tilts[["date", "macro_tilt"]], on="date", how="left")
    out["macro_tilt"] = out["macro_tilt"].fillna(0.0)
    new_sig = []
    for _, r in out.iterrows():
        eng = {
            "detected_regime": r["detected_regime"],
            "cascade_p": float(r["cascade_p"]),
            "mom5": float(r["mom5"]),
            "macro_tilt": float(r["macro_tilt"]),
            "alt_tilt": 0.0,  # no long-span stablecoin proxy; macro-only audit
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
    tilts = build_content_tilts(macro)
    print("tilt days", len(tilts), "risk-on share", round(float((tilts["macro_tilt"] > 0).mean()), 3),
          "risk-off share", round(float((tilts["macro_tilt"] < 0).mean()), 3))

    with_content = inject_content(panel, tilts)
    n_changed = int((with_content["signal"].to_numpy() != panel["signal"].to_numpy()).sum())
    print("signals changed by content:", n_changed, "of", len(panel))

    curves = {
        "mechanism+macro_content": policy_daily(with_content, "mechanism"),
        "mechanism (no content)": policy_daily(panel, "mechanism"),
        "momentum": policy_daily(panel, "momentum"),
        "always_long": policy_daily(panel, "always_long"),
    }
    summary = pd.DataFrame([{"policy": k, **ann_stats(v)} for k, v in curves.items()])
    summary.to_csv(TAB / "table_longspan_content_summary.csv", index=False)
    print(summary.to_string(index=False))

    boots = {}
    for name, a, b in [
        ("content_minus_nocontent", "mechanism+macro_content", "mechanism (no content)"),
        ("content_minus_momentum", "mechanism+macro_content", "momentum"),
        ("nocontent_minus_momentum", "mechanism (no content)", "momentum"),
    ]:
        for method in ("circular", "stationary"):
            boots[f"{name}_{method}"] = bootstrap_delta_pvalues(
                curves[a], curves[b], n_boot=999, block=5, method=method
            )
    (TAB / "table_longspan_content_bootstrap.json").write_text(
        json.dumps(
            {
                "disclosure": (
                    "Yahoo VIX/DXY closes, same-evening publication, one-day lag; "
                    "proxy for vintaged macro content over 2017+; macro-only (no alt band)."
                ),
                "n_signals_changed": n_changed,
                **boots,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    for k, v in boots.items():
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
                "tilt_active_share": round(float((gc["macro_tilt"] != 0).mean()), 3),
            }
        )
    by_year = pd.DataFrame(rows)
    by_year.to_csv(TAB / "table_longspan_content_by_year.csv", index=False)
    print(by_year.to_string(index=False))
    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
