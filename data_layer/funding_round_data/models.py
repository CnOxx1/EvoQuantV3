"""funding_round_data 数据模型。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class FundingRound:
    """融资轮次数据。"""
    project: str               # 项目名称
    round_type: str            # 融资轮次类型 (seed/series_a/series_b/...)
    amount_usd: float          # 融资金额 (USD)
    valuation: float           # 估值 (USD)
    lead_investors: str        # 领投方（逗号分隔）
    date: str                  # 融资日期 (ISO 8601)
    category: str              # 项目类别 (defi/nft/infra/...)
    chain: str                 # 所在链 (ethereum/solana/multi/...)


@dataclass(frozen=True)
class InvestorActivity:
    """投资者活动数据。"""
    investor: str              # 投资机构名称
    rounds_count: int          # 参与轮次数
    total_invested_usd: float  # 总投资金额 (USD)
    categories: str            # 投资类别（逗号分隔）
    collected_at: str          # 采集时间 (ISO 8601)
