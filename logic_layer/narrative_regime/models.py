"""narrative_regime 数据模型。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MarketNarrative:
    """市场叙事状态。"""
    ts: str
    narrative_id: str
    narrative_name: str
    lifecycle_phase: str       # emerging / growing / peak / decaying
    attention_score: float     # 0-100
    capital_flow_correlation: float
    related_tokens: str        # JSON list


@dataclass(frozen=True)
class NarrativeTransition:
    """叙事阶段转换记录。"""
    ts: str
    narrative_id: str
    from_phase: str
    to_phase: str
    trigger_event: str
