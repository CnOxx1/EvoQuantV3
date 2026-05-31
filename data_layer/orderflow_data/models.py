"""orderflow_data 数据模型。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class TradeFlow:
    """逐笔成交流记录。"""
    exchange: str          # binance, bybit, okx
    symbol: str            # BTCUSDT
    entity_key: str        # BTC
    trade_time: str        # ISO 8601
    price: float
    quantity: float
    side: str              # buy, sell
    is_maker: bool         # 是否为挂单方
    trade_id: str


@dataclass(frozen=True)
class OrderFlowAggregation:
    """某实体在某时间窗口的订单流聚合。"""
    entity_key: str
    exchange: str
    interval: str          # 1m, 5m, 15m, 1h
    window_start: str
    window_end: str
    buy_volume: float      # 主动买入量
    sell_volume: float     # 主动卖出量
    cvd: float             # 累积成交量差 (buy - sell)
    large_buy_count: int   # 大单买入次数 (>$100K)
    large_sell_count: int  # 大单卖出次数
    large_buy_volume: float
    large_sell_volume: float
    vwap: float            # 成交量加权均价
    trade_count: int       # 总成交笔数
    aggression_ratio: float  # 主动买/主动卖比率
