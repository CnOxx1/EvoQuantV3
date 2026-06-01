"""alpha_decay 数据模型。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SignalDecay:
    """信号衰减分析。"""
    ts: str
    signal_name: str
    module_source: str
    half_life_hours: float
    autocorrelation: float
    current_strength: float
    decay_rate: float


@dataclass(frozen=True)
class CrowdingIndex:
    """信号拥挤度指标。"""
    ts: str
    crowding_score: float      # 0-100
    agreeing_signals: int
    disagreeing_signals: int
    contrarian_signal: str     # 最强反向信号名称
    signal_surprise_index: float
