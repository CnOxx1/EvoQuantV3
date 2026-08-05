#!/usr/bin/env python3
"""Block-bootstrap CE inference for live Ungated on the open slice (WMI>=0.05).

Zero API cost: reuses full-OOS Ungated checkpoints under pdf/sci/llm_consumer/transcripts/.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pdf.sci.llm_consumer.eval import TRANSCRIPT_DIR, _ensure_panel
from pdf.sci.run_jf_experiments import (
    _sharpe_ce_from_daily,
    block_bootstrap_indices,
    portfolio_stats,
    split_is_oos,
)

TAB = Path(__file__).resolve().parent / "tables"
TAB_ROOT = ROOT / "pdf" / "tables"
MODELS = [
    "gpt-5.4-mini",
    "deepseek-v4-flash",
    "glm-5.2",
    "gemini-3.5-flash-lite",
]


def _action_to_pos(action: str) -> float:
    a = (action or "").lower()
    if a == "bullish":
        return 1.0
    if a == "bearish":
        return -1.0
    return 0.0


def _load_open_merged(model: str, open_keys: set[tuple[str, str]], oos: pd.DataFrame) -> pd.DataFrame:
    ckpt = TRANSCRIPT_DIR / f"{model}_full_ungated.ckpt.jsonl"
    if not ckpt.exists():
        raise FileNotFoundError(ckpt)
    recs = []
    for line in ckpt.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if str(r.get("rationale", "")).startswith("provider-error"):
            continue
        if (r["date"], r["asset"]) not in open_keys:
            continue
        pos = float(r["position"]) if "position" in r else _action_to_pos(r.get("action", "abstain"))
        recs.append(
            {
                "date_s": r["date"],
                "asset": r["asset"],
                "action": r.get("action"),
                "position": pos,
            }
        )
    tdf = pd.DataFrame(recs)
    oos2 = oos.copy()
    oos2["date_s"] = oos2["date"].astype(str).str[:10]
    m = oos2.merge(tdf, on=["date_s", "asset"], how="inner")
    m = m.rename(columns={"date": "date_ts"})
    m["date"] = pd.to_datetime(m["date_s"])
    return m.sort_values(["date", "asset"])


def _daily_pnl(m: pd.DataFrame) -> pd.Series:
    st_tmp = m[["date", "asset", "ret"]].copy()
    pos = m["position"].astype(float)
    # reuse portfolio_stats path for consistency, but also return daily
    tmp = st_tmp.copy()
    tmp["pos"] = pos.values
    tmp["pnl"] = tmp["pos"] * tmp["ret"]
    return tmp.groupby("date")["pnl"].mean().sort_index()


def _p_ce_positive(daily: pd.Series, *, n_boot: int, block: int, seed: int) -> dict:
    """Test H0: CE = 0 (two-sided) and report one-sided evidence CE > 0."""
    daily = daily.astype(float).sort_index()
    n = len(daily)
    sh, ce = _sharpe_ce_from_daily(daily)
    rng = np.random.default_rng(seed)
    boots = block_bootstrap_indices(n, block, n_boot, rng)
    vals = daily.to_numpy()
    boot_ce = np.empty(n_boot)
    boot_sh = np.empty(n_boot)
    for i in range(n_boot):
        boot_sh[i], boot_ce[i] = _sharpe_ce_from_daily(pd.Series(vals[boots[i]]))
    # two-sided percentile p for CE around 0
    left = (np.sum(boot_ce <= 0) + 1) / (n_boot + 1)
    right = (np.sum(boot_ce >= 0) + 1) / (n_boot + 1)
    p_two = float(min(1.0, 2.0 * min(left, right)))
    # one-sided: P*(CE* <= 0)
    p_gt = float((np.sum(boot_ce <= 0) + 1) / (n_boot + 1))
    return {
        "n_days": n,
        "CE": round(float(ce), 4),
        "Sharpe": round(float(sh), 3),
        "p_CE_two_sided": round(p_two, 4),
        "p_CE_gt0": round(p_gt, 4),
        "ci_CE_05": round(float(np.quantile(boot_ce, 0.025)), 4),
        "ci_CE_95": round(float(np.quantile(boot_ce, 0.975)), 4),
        "n_boot": n_boot,
        "block": block,
    }


def main() -> int:
    panel = _ensure_panel()
    _, oos, cut = split_is_oos(panel)
    open_ = oos[oos["WMI"].astype(float) >= 0.05].copy()
    open_keys = set(zip(open_["date"].astype(str).str[:10], open_["asset"]))
    print("cut", cut, "open n", len(open_))

    n_boot, block, seed = 999, 5, 20260805
    rows = []
    vendor_dailies = []
    for model in MODELS:
        m = _load_open_merged(model, open_keys, oos)
        daily = _daily_pnl(m)
        st = portfolio_stats(m, m["position"].astype(float))
        inf = _p_ce_positive(daily, n_boot=n_boot, block=block, seed=seed)
        act = m[m["position"].astype(float) != 0.0]
        act_ce = (
            portfolio_stats(act, act["position"].astype(float))["CE"] if len(act) else float("nan")
        )
        row = {
            "model": model,
            "n": int(len(m)),
            "n_days": inf["n_days"],
            "abstain": round(float(st["abstain_rate"]), 4),
            "CE": inf["CE"],
            "Sharpe": inf["Sharpe"],
            "act_conditional_CE": None if act_ce != act_ce else round(float(act_ce), 4),
            "p_CE_gt0": inf["p_CE_gt0"],
            "p_CE_two_sided": inf["p_CE_two_sided"],
            "ci_CE_05": inf["ci_CE_05"],
            "ci_CE_95": inf["ci_CE_95"],
            "n_boot": n_boot,
            "block": block,
        }
        rows.append(row)
        vendor_dailies.append(daily.rename(model))
        print(model, row)

    # Equal-weight cross-vendor mean daily pnl on intersecting dates
    aligned = pd.concat(vendor_dailies, axis=1, join="inner")
    mean_daily = aligned.mean(axis=1)
    mean_inf = _p_ce_positive(mean_daily, n_boot=n_boot, block=block, seed=seed + 1)
    mean_row = {
        "model": "mean_equal_vendor",
        "n": int(aligned.notna().all(axis=1).sum() * aligned.shape[1]),  # rough
        "n_days": mean_inf["n_days"],
        "abstain": None,
        "CE": mean_inf["CE"],
        "Sharpe": mean_inf["Sharpe"],
        "act_conditional_CE": None,
        "p_CE_gt0": mean_inf["p_CE_gt0"],
        "p_CE_two_sided": mean_inf["p_CE_two_sided"],
        "ci_CE_05": mean_inf["ci_CE_05"],
        "ci_CE_95": mean_inf["ci_CE_95"],
        "n_boot": n_boot,
        "block": block,
    }
    rows.append(mean_row)
    print("MEAN", mean_row)

    out = pd.DataFrame(rows)
    for path in (TAB / "table_llm_open_ungated_ce_bootstrap.csv", TAB_ROOT / "table_llm_open_ungated_ce_bootstrap.csv"):
        path.parent.mkdir(parents=True, exist_ok=True)
        out.to_csv(path, index=False)
        print("wrote", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
