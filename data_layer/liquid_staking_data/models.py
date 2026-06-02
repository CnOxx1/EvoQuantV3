"""liquid_staking_data 数据模型。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class StakingPosition:
    """流动性质押仓位数据。"""
    protocol: str              # 协议名称 (lido/rocketpool)
    total_staked: float        # 总质押量 (ETH)
    staking_apr: float         # 质押年化收益率
    lst_premium_discount: float  # LST 溢价/折价率
    timestamp: str             # ISO 8601


@dataclass(frozen=True)
class ValidatorQueue:
    """验证者队列数据。"""
    queue_entry_wait: float    # 进入队列等待时间 (小时)
    queue_exit_wait: float     # 退出队列等待时间 (小时)
    active_validators: int     # 活跃验证者数量
    pending_validators: int    # 待激活验证者数量
    timestamp: str             # ISO 8601


@dataclass(frozen=True)
class RestakingTVL:
    """再质押 TVL 数据。"""
    protocol: str              # 协议名称 (eigenlayer)
    restaking_tvl: float       # 再质押 TVL (USD)
    num_operators: int         # 运营商数量
    num_avs: int               # AVS 数量
    timestamp: str             # ISO 8601
