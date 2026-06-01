"""governance_data 数据模型。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class GovernanceProposal:
    """DAO 治理提案数据。"""
    protocol: str              # 协议名称 (如 aave.eth)
    proposal_id: str           # 提案 ID
    title: str                 # 提案标题
    state: str                 # 提案状态 (active/closed/pending)
    votes_for: float           # 赞成票数
    votes_against: float       # 反对票数
    quorum_pct: float          # 法定人数达成百分比
    start_ts: str              # 开始时间 ISO 8601
    end_ts: str                # 结束时间 ISO 8601


@dataclass(frozen=True)
class GovernanceVote:
    """单个治理投票记录。"""
    protocol: str              # 协议名称
    proposal_id: str           # 提案 ID
    voter: str                 # 投票者地址
    voting_power: float        # 投票权重
    choice: str                # 投票选择
    timestamp: str             # 投票时间 ISO 8601


@dataclass(frozen=True)
class GovernanceActivity:
    """协议治理活跃度指标。"""
    protocol: str              # 协议名称
    proposals_active: int      # 活跃提案数
    participation_rate: float  # 参与率
    whale_vote_pct: float      # 巨鲸投票占比
    timestamp: str             # 统计时间 ISO 8601
