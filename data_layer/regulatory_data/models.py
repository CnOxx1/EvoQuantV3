"""regulatory_data 数据模型。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class RegulatoryEvent:
    """单条监管事件记录。"""
    event_id: str
    jurisdiction: str      # US, EU, CN, UK, JP, KR, global
    regulator: str         # SEC, CFTC, ECB, MiCA, HKMA
    event_type: str        # enforcement, guidance, legislation, etf_decision, license
    title: str
    summary: str
    impact_scope: str      # market_wide, sector, single_asset
    impact_severity: str   # high, medium, low
    affected_assets: str   # 逗号分隔的受影响标的
    event_date: str        # ISO 8601
    source_url: str


@dataclass(frozen=True)
class ETFStatus:
    """ETF 审批状态追踪。"""
    etf_name: str          # BlackRock iShares Bitcoin ETF
    asset: str             # BTC, ETH, SOL
    jurisdiction: str      # US, HK, EU
    applicant: str         # BlackRock, Fidelity, etc.
    status: str            # filed, under_review, approved, rejected, withdrawn
    filing_date: str
    decision_deadline: str
    last_update: str
    notes: str
