"""prediction_market_data 数据模型。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class PredictionMarket:
    """预测市场活跃合约数据。"""
    market_id: str             # 市场唯一标识
    question: str              # 市场问题描述
    outcome_yes_price: float   # YES 结果价格 (0-1)
    outcome_no_price: float    # NO 结果价格 (0-1)
    volume_24h: float          # 24h 交易量 (USD)
    liquidity: float           # 流动性 (USD)
    end_date: str              # 市场结束日期 (ISO 8601)
    category: str              # 市场分类
    timestamp: str             # 采集时间 (ISO 8601)


@dataclass(frozen=True)
class PredictionMarketHistory:
    """预测市场历史价格数据。"""
    market_id: str             # 市场唯一标识
    question: str              # 市场问题描述
    outcome_yes_price: float   # YES 结果价格 (0-1)
    outcome_no_price: float    # NO 结果价格 (0-1)
    volume_24h: float          # 24h 交易量 (USD)
    liquidity: float           # 流动性 (USD)
    timestamp: str             # 记录时间 (ISO 8601)
