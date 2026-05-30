from __future__ import annotations

import re

import pandas as pd


TIMEFRAME_PATTERN = re.compile(r"^(?P<count>\d+)(?P<unit>[mhdw])$")


def timeframe_to_timedelta(timeframe: str) -> pd.Timedelta:
    match = TIMEFRAME_PATTERN.fullmatch(timeframe)
    if not match:
        raise ValueError(f"不支持的 timeframe: {timeframe}")

    count = int(match.group("count"))
    unit = match.group("unit")
    unit_map = {
        "m": "minutes",
        "h": "hours",
        "d": "days",
        "w": "weeks",
    }
    return pd.Timedelta(**{unit_map[unit]: count})


def bars_to_timedelta(timeframe: str, bars: int) -> pd.Timedelta:
    return timeframe_to_timedelta(timeframe) * bars
