"""nft_market_data 数据模型。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class NftCollectionStats:
    """单个 NFT 集合的统计数据。"""
    collection: str
    floor_price_eth: float
    volume_24h_eth: float
    sales_count: int
    unique_buyers: int
    unique_sellers: int
    wash_trade_pct: float
    listed_pct: float
    timestamp: str


@dataclass(frozen=True)
class NftMarketMetrics:
    """NFT 市场整体指标。"""
    total_volume_24h_eth: float
    total_sales_count: int
    blue_chip_index: float
    avg_floor_change_pct: float
    timestamp: str
