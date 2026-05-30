"""Pydantic response models for API endpoints."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class HealthSummary(BaseModel):
    status: str
    wmi: float | None = None
    interpretation: str | None = None
    should_ai_abstain: bool | None = None
    measured_at: str | None = None
    domains: dict[str, Any] = {}
    summary: dict[str, Any] = {}


class SymbolInfo(BaseModel):
    symbol: str
    tier: str
    sector: str


class SymbolsResponse(BaseModel):
    count: int
    symbols: list[SymbolInfo]


class DomainListItem(BaseModel):
    name: str
    status: str
    latest_data_time: str | None = None
    latency_seconds: float | None = None


class DomainsListResponse(BaseModel):
    domains: list[DomainListItem]


class TimeSliceRequest(BaseModel):
    timestamp: str
    symbols: list[str] | None = None
    domains: list[str] | None = None


class FeatureHistoryRequest(BaseModel):
    symbol: str
    start: str
    end: str
    features: list[str] | None = None
    source: str = "technical_indicators"
    timeframe: str = "1h"
