"""token_unlock_realtime 数据模型。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class UpcomingUnlock:
    """即将到来的代币解锁事件。"""
    project: str               # 项目名称
    token: str                 # 代币符号
    unlock_date: str           # 解锁日期 (ISO 8601)
    amount_tokens: float       # 解锁代币数量
    amount_usd: float          # 解锁金额 (USD)
    unlock_type: str           # 解锁类型 (cliff/linear/team/investor 等)
    pct_of_supply: float       # 占总供应量百分比
    days_until: int            # 距解锁天数


@dataclass(frozen=True)
class UnlockEvent:
    """已发生的代币解锁事件。"""
    project: str               # 项目名称
    token: str                 # 代币符号
    unlock_date: str           # 解锁日期 (ISO 8601)
    amount_tokens: float       # 解锁代币数量
    amount_usd: float          # 解锁金额 (USD)
    unlock_type: str           # 解锁类型
    actual_price_impact: float # 实际价格影响 (百分比)
    timestamp: str             # 记录时间 (ISO 8601)
