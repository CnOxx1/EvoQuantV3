"""Load and hash the versioned JF/RFS experiment configuration."""

from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

CONFIG_PATH = Path(__file__).resolve().parent / "experiment_config.json"


def config_content_hash(raw: bytes | None = None) -> str:
    data = CONFIG_PATH.read_bytes() if raw is None else raw
    return hashlib.sha256(data).hexdigest()[:16]


@lru_cache(maxsize=1)
def load_experiment_config() -> dict[str, Any]:
    raw = CONFIG_PATH.read_bytes()
    cfg = json.loads(raw.decode("utf-8"))
    cfg["_content_hash"] = config_content_hash(raw)
    cfg["_path"] = str(CONFIG_PATH)
    return cfg


def paper_assets() -> list[str]:
    return list(load_experiment_config()["assets"])


def asset_to_symbol() -> dict[str, str]:
    return dict(load_experiment_config()["asset_to_symbol"])


def bootstrap_symbols() -> list[str]:
    return list(load_experiment_config()["bootstrap_symbols"])


def hist_bands() -> list[str]:
    return list(load_experiment_config()["hist_bands"])


def content_bands() -> dict[str, str]:
    return dict(load_experiment_config()["content_bands"])


def decision_asof_for_payoff_date(payoff_date) -> "pd.Timestamp":  # type: ignore[name-defined]
    """Return the PIT decision clock for a payoff calendar day.

    Protocol ``decision_at_prev_close``: features for earning r_t use information
    available at (t-1) 23:59, never same-day close.
    """
    import pandas as pd

    cfg = load_experiment_config()["timing"]
    offset = int(cfg.get("decision_asof_offset_days", -1))
    clock = str(cfg.get("decision_asof_clock", "23:59:00"))
    hh, mm, ss = (int(x) for x in clock.split(":"))
    base = pd.Timestamp(payoff_date).normalize() + pd.Timedelta(days=offset)
    return base + pd.Timedelta(hours=hh, minutes=mm, seconds=ss)


def config_manifest() -> dict[str, Any]:
    cfg = load_experiment_config()
    return {
        "name": cfg["name"],
        "version": cfg["version"],
        "content_hash": cfg["_content_hash"],
        "path": cfg["_path"],
        "pre_specified_contrast": cfg["pre_specified_contrast"],
        "timing": cfg["timing"],
    }
