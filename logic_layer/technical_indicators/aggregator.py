from __future__ import annotations

from typing import Iterable

import pandas as pd
from loguru import logger


MERGE_METHOD = "volume_weighted_ohlc_v1"


class MultiExchangeKlineAggregator:
    """将多交易所K线聚合为统一主时间序列。"""

    REQUIRED_COLUMNS = [
        "symbol",
        "exchange",
        "timeframe",
        "open_time",
        "open",
        "high",
        "low",
        "close",
        "volume",
    ]

    def merge(self, rows: Iterable[dict]) -> pd.DataFrame:
        frame = pd.DataFrame(list(rows))
        if frame.empty:
            return pd.DataFrame(
                columns=[
                    "symbol",
                    "timeframe",
                    "open_time",
                    "open",
                    "high",
                    "low",
                    "close",
                    "volume",
                    "exchange_count",
                    "source_exchanges",
                    "merge_method",
                ]
            )

        missing_columns = [
            column for column in self.REQUIRED_COLUMNS if column not in frame.columns
        ]
        if missing_columns:
            raise ValueError(f"K线聚合缺少字段: {missing_columns}")

        frame["open_time"] = pd.to_datetime(frame["open_time"], utc=True, errors="coerce")
        for column in ["open", "high", "low", "close", "volume"]:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")

        frame = frame.dropna(subset=self.REQUIRED_COLUMNS)
        frame = frame.sort_values(["symbol", "timeframe", "open_time", "exchange"])
        if frame.empty:
            return frame

        merged_records: list[dict] = []
        for (symbol, timeframe, open_time), group in frame.groupby(
            ["symbol", "timeframe", "open_time"],
            sort=True,
        ):
            weights = group["volume"].clip(lower=0.0)
            if weights.sum() <= 0:
                weights = pd.Series(1.0, index=group.index)

            merged_records.append({
                "symbol": symbol,
                "timeframe": timeframe,
                "open_time": open_time,
                "open": float((group["open"] * weights).sum() / weights.sum()),
                "high": float(group["high"].max()),
                "low": float(group["low"].min()),
                "close": float((group["close"] * weights).sum() / weights.sum()),
                "volume": float(group["volume"].sum()),
                "exchange_count": int(group["exchange"].nunique()),
                "source_exchanges": ",".join(sorted(group["exchange"].unique())),
                "merge_method": MERGE_METHOD,
            })

        merged = pd.DataFrame(merged_records).sort_values(
            ["symbol", "timeframe", "open_time"]
        )
        logger.info(f"已合并生成 {len(merged)} 条统一K线")
        return merged
