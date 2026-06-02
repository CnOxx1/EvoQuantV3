"""whale_wallet_pnl 数据模型。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class WhalePortfolio:
    """巨鲸钱包投资组合快照。"""
    address: str               # 钱包地址
    label: str                 # 钱包标签 (基金名/机构名/匿名)
    total_value_usd: float     # 总资产价值 (USD)
    pnl_24h: float             # 24小时 PnL (USD)
    pnl_7d: float              # 7天 PnL (USD)
    pnl_30d: float             # 30天 PnL (USD)
    top_holdings_json: str     # 前N大持仓 (JSON 序列化)
    unrealized_pnl_pct: float  # 未实现 PnL 百分比
    realized_pnl_24h: float    # 24小时已实现 PnL (USD)
    timestamp: str             # 采集时间 (ISO 8601)


@dataclass(frozen=True)
class WhalePnlHistory:
    """巨鲸钱包每日 PnL 历史。"""
    address: str               # 钱包地址
    date: str                  # 日期 (YYYY-MM-DD)
    total_value_usd: float     # 当日总资产价值 (USD)
    pnl_daily: float           # 当日 PnL (USD)
    cumulative_pnl: float      # 累计 PnL (USD)
