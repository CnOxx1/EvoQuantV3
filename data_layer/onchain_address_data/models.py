"""链上地址行为数据模型。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class AddressLabel:
    """地址标签/画像信息。"""
    address: str               # 链上地址
    label: str                 # 标签名称（如 "Binance Hot Wallet"）
    entity: str                # 所属实体（如 "Binance"）
    category: str              # 分类（exchange, fund, whale, defi, etc.）
    first_seen: str            # 首次活跃时间 ISO 8601
    last_active: str           # 最近活跃时间 ISO 8601


@dataclass(frozen=True)
class AddressFlow:
    """地址资金流动记录。"""
    address: str               # 关联地址
    token: str                 # 代币符号（ETH, USDT, etc.）
    direction: str             # 方向: inflow / outflow
    amount_usd: float          # USD 金额
    counterparty: str          # 对手方地址
    tx_hash: str               # 交易哈希
    timestamp: str             # ISO 8601


@dataclass(frozen=True)
class WhaleMoveEvent:
    """巨鲸异动事件。"""
    address: str               # 巨鲸地址
    entity: str                # 实体名称
    token: str                 # 代币符号
    amount_usd: float          # USD 金额
    direction: str             # 方向: deposit / withdrawal / transfer
    from_exchange: str         # 来源交易所（如有）
    to_exchange: str           # 目标交易所（如有）
    timestamp: str             # ISO 8601
