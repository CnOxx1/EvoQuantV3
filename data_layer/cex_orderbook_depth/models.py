"""cex_orderbook_depth 数据模型。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class DepthSnapshot:
    """CEX 深度盘口聚合快照。"""
    symbol: str                # 交易对 (BTC/USDT 等)
    exchange: str              # 交易所 (binance/okx/bybit)
    timestamp: str             # 采集时间 (ISO 8601)
    bid_volume_total: float    # 买盘总量
    ask_volume_total: float    # 卖盘总量
    depth_imbalance_1pct: float  # 1% 价格范围内买卖不平衡度
    depth_imbalance_5pct: float  # 5% 价格范围内买卖不平衡度
    buy_wall_price: float      # 买墙价格
    buy_wall_size: float       # 买墙规模
    sell_wall_price: float     # 卖墙价格
    sell_wall_size: float      # 卖墙规模
    mid_price: float           # 中间价


@dataclass(frozen=True)
class DepthLevel:
    """CEX 深度盘口单档数据。"""
    symbol: str                # 交易对
    exchange: str              # 交易所
    timestamp: str             # 采集时间 (ISO 8601)
    side: str                  # 方向 (bid/ask)
    price_level: float         # 价格档位
    volume: float              # 该档位数量
    cumulative_volume: float   # 累计数量
