"""stablecoin_flow_data 数据模型。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class StablecoinMintBurn:
    """稳定币 Mint/Burn 事件数据。"""
    asset: str                 # 稳定币名称 (USDT/USDC/DAI 等)
    event_type: str            # 事件类型 (mint/burn)
    amount_usd: float          # 事件金额 (USD)
    chain: str                 # 所在链 (ethereum/tron/bsc 等)
    tx_hash: str               # 交易哈希
    block_number: int          # 区块号
    timestamp: str             # 事件时间 (ISO 8601)
    from_address: str          # 发送地址
    to_address: str            # 接收地址


@dataclass(frozen=True)
class StablecoinChainFlow:
    """稳定币链间净流数据。"""
    asset: str                 # 稳定币名称
    chain: str                 # 链名称
    net_flow_usd: float        # 净流入/流出 (正=流入, 负=流出)
    total_supply_on_chain: float  # 该链上总供应量
    timestamp: str             # 采集时间 (ISO 8601)
