from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


def utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class MarketInfo(BaseModel):
    """交易对静态基础信息"""
    symbol: str = Field(..., description="交易对标识，如 BTC/USDT")
    exchange_symbol: Optional[str] = Field(default=None, description="交易所原生交易对标识，如 BTCUSDT")
    base: str = Field(..., description="基础币种，如 BTC")
    quote: str = Field(..., description="计价币种，如 USDT")
    exchange: str = Field(..., description="交易所名称，如 binance")
    market_type: str = Field(default="spot", description="市场类型: spot/swap/futures")
    status: Optional[str] = Field(default=None, description="交易对状态: active/suspended")
    is_spot: Optional[bool] = Field(default=None, description="是否现货市场")
    is_margin: Optional[bool] = Field(default=None, description="是否支持杠杆")
    is_swap: Optional[bool] = Field(default=None, description="是否永续合约")
    is_future: Optional[bool] = Field(default=None, description="是否交割合约")
    is_contract: Optional[bool] = Field(default=None, description="是否合约产品")
    is_linear: Optional[bool] = Field(default=None, description="是否线性合约")
    is_inverse: Optional[bool] = Field(default=None, description="是否反向合约")
    price_precision: Optional[float] = Field(default=None, description="价格精度（小数位数或最小精度值，取决于交易所）")
    min_price: Optional[float] = Field(default=None, description="最小下单价格")
    max_price: Optional[float] = Field(default=None, description="最大下单价格")
    amount_precision: Optional[float] = Field(default=None, description="数量精度（小数位数或最小精度值，取决于交易所）")
    min_amount: Optional[float] = Field(default=None, description="最小下单量")
    max_amount: Optional[float] = Field(default=None, description="最大下单量")
    min_cost: Optional[float] = Field(default=None, description="最小下单金额")
    max_cost: Optional[float] = Field(default=None, description="最大下单金额")
    maker_fee: Optional[float] = Field(default=None, description="Maker手续费率")
    taker_fee: Optional[float] = Field(default=None, description="Taker手续费率")
    contract_size: Optional[float] = Field(default=None, description="合约面值")
    settle_currency: Optional[str] = Field(default=None, description="结算币种")
    raw_info_json: Optional[str] = Field(default=None, description="交易所原始字段JSON，供后续扩展")
    updated_at: datetime = Field(default_factory=utc_now_naive, description="更新时间")


class Ticker(BaseModel):
    """实时行情数据"""
    symbol: str = Field(..., description="交易对标识")
    exchange: str = Field(..., description="交易所名称")
    last_price: Optional[float] = Field(default=None, description="最新成交价")
    open_24h: Optional[float] = Field(default=None, description="24h开盘价")
    bid: Optional[float] = Field(default=None, description="买一价")
    bid_volume: Optional[float] = Field(default=None, description="买一量")
    ask: Optional[float] = Field(default=None, description="卖一价")
    ask_volume: Optional[float] = Field(default=None, description="卖一量")
    previous_close: Optional[float] = Field(default=None, description="上一收盘价")
    high_24h: Optional[float] = Field(default=None, description="24h最高价")
    low_24h: Optional[float] = Field(default=None, description="24h最低价")
    vwap_24h: Optional[float] = Field(default=None, description="24h成交量加权平均价")
    volume_24h: Optional[float] = Field(default=None, description="24h成交量(base)")
    quote_volume_24h: Optional[float] = Field(default=None, description="24h成交额(quote)")
    change_abs_24h: Optional[float] = Field(default=None, description="24h绝对涨跌")
    change_24h: Optional[float] = Field(default=None, description="24h涨跌幅(%)")
    mid_price: Optional[float] = Field(default=None, description="盘口中间价")
    spread: Optional[float] = Field(default=None, description="买卖价差")
    spread_bps: Optional[float] = Field(default=None, description="买卖价差（基点）")
    timestamp: datetime = Field(default_factory=utc_now_naive, description="行情时间戳")


class Kline(BaseModel):
    """K线数据"""
    symbol: str = Field(..., description="交易对标识")
    exchange: str = Field(..., description="交易所名称")
    timeframe: str = Field(..., description="K线周期: 1m/5m/15m/1h/4h/1d")
    open_time: datetime = Field(..., description="开盘时间")
    open: float = Field(..., description="开盘价")
    high: float = Field(..., description="最高价")
    low: float = Field(..., description="最低价")
    close: float = Field(..., description="收盘价")
    volume: float = Field(..., description="成交量")


class OrderBookLevel(BaseModel):
    """订单簿单档位"""
    price: float = Field(..., description="价格")
    amount: float = Field(..., description="数量")


class OrderBook(BaseModel):
    """深度数据"""
    symbol: str = Field(..., description="交易对标识")
    exchange: str = Field(..., description="交易所名称")
    snapshot_depth: int = Field(default=20, description="快照采样档位数")
    bids: list[OrderBookLevel] = Field(default_factory=list, description="买盘列表（价格降序）")
    asks: list[OrderBookLevel] = Field(default_factory=list, description="卖盘列表（价格升序）")
    best_bid: Optional[float] = Field(default=None, description="买一价")
    best_ask: Optional[float] = Field(default=None, description="卖一价")
    mid_price: Optional[float] = Field(default=None, description="盘口中间价")
    spread: Optional[float] = Field(default=None, description="买卖价差")
    spread_bps: Optional[float] = Field(default=None, description="买卖价差（基点）")
    bid_depth_notional: Optional[float] = Field(default=None, description="买盘前N档名义价值总和（quote）")
    ask_depth_notional: Optional[float] = Field(default=None, description="卖盘前N档名义价值总和（quote）")
    depth_imbalance: Optional[float] = Field(default=None, description="前N档买卖盘不平衡度")
    timestamp: datetime = Field(default_factory=utc_now_naive, description="快照时间戳")


class FundingRate(BaseModel):
    """资金费率"""
    symbol: str = Field(..., description="交易对标识")
    exchange: str = Field(..., description="交易所名称")
    funding_rate: Optional[float] = Field(default=None, description="当期资金费率")
    mark_price: Optional[float] = Field(default=None, description="标记价格")
    index_price: Optional[float] = Field(default=None, description="指数价格")
    next_funding_time: Optional[datetime] = Field(default=None, description="下次结算时间")
    timestamp: datetime = Field(default_factory=utc_now_naive, description="采集时间戳")


class TradeFlowBar(BaseModel):
    """成交与主动买卖流聚合 bar。"""

    symbol: str = Field(..., description="交易对标识")
    exchange: str = Field(..., description="交易所名称")
    market_type: str = Field(default="spot", description="市场类型")
    interval: str = Field(default="1m", description="bar 周期")
    open_time: datetime = Field(..., description="bar 起始时间")
    trade_count: int = Field(default=0, description="成交笔数")
    buy_trade_count: int = Field(default=0, description="买向成交笔数")
    sell_trade_count: int = Field(default=0, description="卖向成交笔数")
    buy_notional: float = Field(default=0.0, description="买向成交额")
    sell_notional: float = Field(default=0.0, description="卖向成交额")
    aggressive_buy_notional: float = Field(default=0.0, description="主动买入成交额")
    aggressive_sell_notional: float = Field(default=0.0, description="主动卖出成交额")
    net_taker_notional: float = Field(default=0.0, description="主动买卖净额")
    cvd: float = Field(default=0.0, description="累积成交量差代理")
    avg_trade_notional: float = Field(default=0.0, description="平均单笔成交额")
    largest_trade_notional: float = Field(default=0.0, description="最大单笔成交额")
    collected_at: datetime = Field(default_factory=utc_now_naive, description="采集时间")
    raw_payload_json: Optional[str] = Field(default=None, description="原始明细 JSON")


class OpenInterestSnapshot(BaseModel):
    """持仓量快照。"""

    symbol: str = Field(..., description="交易对标识")
    exchange: str = Field(..., description="交易所名称")
    market_type: str = Field(default="linear_swap", description="市场类型")
    interval: str = Field(default="5m", description="标准化频率")
    timestamp: datetime = Field(default_factory=utc_now_naive, description="快照时间")
    open_interest_contracts: Optional[float] = Field(default=None, description="合约张数/币数")
    open_interest_usd: Optional[float] = Field(default=None, description="美元名义价值")
    open_interest_change_5m: Optional[float] = Field(default=None, description="5 分钟变化")
    open_interest_change_1h: Optional[float] = Field(default=None, description="1 小时变化")
    open_interest_change_24h: Optional[float] = Field(default=None, description="24 小时变化")
    raw_payload_json: Optional[str] = Field(default=None, description="原始 payload JSON")


class LiquidationBar(BaseModel):
    """清算聚合 bar。"""

    symbol: str = Field(..., description="交易对标识")
    exchange: str = Field(..., description="交易所名称")
    market_type: str = Field(default="linear_swap", description="市场类型")
    interval: str = Field(default="5m", description="bar 周期")
    open_time: datetime = Field(..., description="bar 起始时间")
    long_liquidation_notional: Optional[float] = Field(default=None, description="多头清算额")
    short_liquidation_notional: Optional[float] = Field(default=None, description="空头清算额")
    long_liquidation_count: Optional[int] = Field(default=None, description="多头清算笔数")
    short_liquidation_count: Optional[int] = Field(default=None, description="空头清算笔数")
    total_liquidation_notional: Optional[float] = Field(default=None, description="总清算额")
    max_single_liquidation_notional: Optional[float] = Field(default=None, description="最大单笔清算额")
    collected_at: datetime = Field(default_factory=utc_now_naive, description="采集时间")
    raw_payload_json: Optional[str] = Field(default=None, description="原始 payload JSON")


class PositioningSnapshot(BaseModel):
    """多空比/账户定位快照。"""

    symbol: str = Field(..., description="交易对标识")
    exchange: str = Field(..., description="交易所名称")
    market_type: str = Field(default="linear_swap", description="市场类型")
    ratio_scope: str = Field(default="accounts", description="比率口径")
    interval: str = Field(default="1h", description="标准化频率")
    timestamp: datetime = Field(default_factory=utc_now_naive, description="快照时间")
    long_ratio: Optional[float] = Field(default=None, description="多头比例")
    short_ratio: Optional[float] = Field(default=None, description="空头比例")
    long_short_ratio: Optional[float] = Field(default=None, description="多空比")
    top_trader_long_ratio: Optional[float] = Field(default=None, description="大户多头比例")
    top_trader_short_ratio: Optional[float] = Field(default=None, description="大户空头比例")
    raw_payload_json: Optional[str] = Field(default=None, description="原始 payload JSON")


class BasisSnapshot(BaseModel):
    """现货/标记/指数 basis 快照。"""

    symbol: str = Field(..., description="交易对标识")
    exchange: str = Field(..., description="交易所名称")
    market_type: str = Field(default="linear_swap", description="市场类型")
    interval: str = Field(default="5m", description="标准化频率")
    timestamp: datetime = Field(default_factory=utc_now_naive, description="快照时间")
    spot_price: Optional[float] = Field(default=None, description="现货价格")
    mark_price: Optional[float] = Field(default=None, description="标记价格")
    index_price: Optional[float] = Field(default=None, description="指数价格")
    basis_abs: Optional[float] = Field(default=None, description="标记-现货绝对价差")
    basis_bps: Optional[float] = Field(default=None, description="标记-现货基点价差")
    annualized_basis_bps: Optional[float] = Field(default=None, description="年化 basis")
    funding_rate: Optional[float] = Field(default=None, description="资金费率")
    next_funding_time: Optional[datetime] = Field(default=None, description="下次 funding 时间")
    raw_payload_json: Optional[str] = Field(default=None, description="原始 payload JSON")
