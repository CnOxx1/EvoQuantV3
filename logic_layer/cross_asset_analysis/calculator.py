"""跨资产计算引擎：相关性矩阵、相对强弱、板块轮动、资金流向。"""

from __future__ import annotations

import math
from datetime import datetime, timezone

import numpy as np


class CrossAssetCalculator:
    """纯计算逻辑，不依赖数据库。"""

    @staticmethod
    def compute_correlation_matrix(
        close_series: dict[str, list[float]],
    ) -> dict[str, dict[str, float]]:
        """从收盘价序列计算 Pearson 相关性矩阵。

        v4.4.0: 使用 numpy 向量化计算替代纯 Python 循环，10-100× 加速。

        Parameters
        ----------
        close_series : dict[str, list[float]]
            {symbol: [close_prices...]}，所有序列等长且时间对齐。

        Returns
        -------
        dict[str, dict[str, float]]
            NxN 相关性矩阵 {symbol_a: {symbol_b: corr}}
        """
        symbols = sorted(close_series.keys())
        n = len(symbols)
        if n < 2:
            return {s: {s: 1.0} for s in symbols}

        # 构建 numpy 矩阵: 每行一个 symbol 的价格序列
        min_len = min(len(close_series[s]) for s in symbols)
        if min_len < 2:
            return {s: {s2: 0.0 for s2 in symbols} for s in symbols}

        price_matrix = np.array(
            [close_series[s][-min_len:] for s in symbols], dtype=np.float64
        )
        # numpy corrcoef 一次计算完整 NxN 矩阵
        corr_np = np.corrcoef(price_matrix)
        # 处理 NaN（如某 symbol 价格恒定导致 std=0）
        corr_np = np.nan_to_num(corr_np, nan=0.0)
        np.clip(corr_np, -1.0, 1.0, out=corr_np)

        # 转换为 dict 格式
        matrix: dict[str, dict[str, float]] = {}
        for i, sym_a in enumerate(symbols):
            matrix[sym_a] = {}
            for j, sym_b in enumerate(symbols):
                matrix[sym_a][sym_b] = round(float(corr_np[i, j]), 4)
        return matrix

    @staticmethod
    def compute_relative_strength(
        returns: dict[str, dict[str, float | None]],
        benchmark: str = "BTC/USDT",
    ) -> list[dict]:
        """计算相对强弱排名。

        Parameters
        ----------
        returns : dict[str, dict[str, float | None]]
            {symbol: {"1d": pct, "3d": pct, "7d": pct}}
        benchmark : str
            基准符号

        Returns
        -------
        list[dict]
            按 7d RS 降序排列的排名列表
        """
        bench = returns.get(benchmark, {})
        bench_7d = bench.get("7d") or 0.0
        bench_3d = bench.get("3d") or 0.0
        bench_1d = bench.get("1d") or 0.0

        entries = []
        for symbol, rets in returns.items():
            r7d = rets.get("7d")
            r3d = rets.get("3d")
            r1d = rets.get("1d")
            rs_7d = (r7d / bench_7d) if (r7d is not None and bench_7d) else None
            rs_3d = (r3d / bench_3d) if (r3d is not None and bench_3d) else None
            rs_1d = (r1d / bench_1d) if (r1d is not None and bench_1d) else None
            entries.append({
                "symbol": symbol,
                "rs_vs_btc_7d": round(rs_7d, 4) if rs_7d is not None else None,
                "rs_vs_btc_3d": round(rs_3d, 4) if rs_3d is not None else None,
                "rs_vs_btc_1d": round(rs_1d, 4) if rs_1d is not None else None,
                "price_change_7d_pct": round(r7d, 4) if r7d is not None else None,
            })

        # 按 7d RS 降序排名
        entries.sort(key=lambda x: x.get("rs_vs_btc_7d") or -999, reverse=True)
        for rank, entry in enumerate(entries, 1):
            entry["rs_rank"] = rank
            rs7 = entry.get("rs_vs_btc_7d")
            rs3 = entry.get("rs_vs_btc_3d")
            if rs7 is not None and rs3 is not None:
                entry["rs_momentum"] = (
                    "rising" if rs7 > rs3 else "falling" if rs7 < rs3 else "stable"
                )
            else:
                entry["rs_momentum"] = "stable"
        return entries

    @staticmethod
    def compute_sector_rotation(
        sector_data: dict[str, dict],
    ) -> list[dict]:
        """计算板块轮动阶段。

        Parameters
        ----------
        sector_data : dict[str, dict]
            {sector: {"return_7d": float, "volatility_7d": float,
                      "net_flow_24h": float, "oi_change_24h": float,
                      "constituent_count": int}}
        """
        entries = []
        for sector, data in sector_data.items():
            ret = data.get("return_7d") or 0.0
            vol = data.get("volatility_7d") or 0.0
            momentum = ret / vol if vol > 0 else 0.0

            # 轮动阶段判定
            if ret > 0 and momentum > 0.5:
                phase = "leading"
            elif ret > 0 and momentum <= 0.5:
                phase = "weakening"
            elif ret <= 0 and momentum > -0.5:
                phase = "improving"
            else:
                phase = "lagging"

            entries.append({
                "sector": sector,
                "sector_return_7d": round(ret, 4),
                "sector_volatility_7d": round(vol, 4),
                "sector_momentum_score": round(momentum, 4),
                "sector_net_flow_24h": data.get("net_flow_24h"),
                "sector_oi_change_24h": data.get("oi_change_24h"),
                "constituent_count": data.get("constituent_count", 0),
                "rotation_phase": phase,
            })
        return entries
