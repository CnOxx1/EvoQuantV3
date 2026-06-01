"""跨场所套利数据模型。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ArbOpportunity:
    """套利机会。"""
    symbol: str
    venue_buy: str
    venue_sell: str
    price_buy: float
    price_sell: float
    spread_bps: float
    estimated_profit_usd: float
    latency_ms: int
    timestamp: str


@dataclass(frozen=True)
class ArbPersistence:
    """套利持续性指标。"""
    symbol: str
    venue_pair: str
    avg_spread_bps: float
    duration_seconds: int
    frequency_per_hour: float
    timestamp: str


@dataclass(frozen=True)
class VenueSpread:
    """场所间价差。"""
    symbol: str
    venue_a: str
    venue_b: str
    mid_spread_bps: float
    bid_ask_cross: bool
    timestamp: str
