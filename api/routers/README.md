# API 路由模块 `api/routers`

## 模块定位

`api/routers` 包含所有 FastAPI 路由定义，每个文件对应一个独立的功能域。路由只负责参数解析、调用底层服务和格式化响应，不包含业务逻辑。

## 模块代码树

```text
api/routers/
  __init__.py               # 包入口
  _helpers.py               # 共享工具函数（符号归一化、DB 连接）
  health.py                 # 健康检查
  bundle.py                 # AI 主 bundle 聚合
  domains.py                # 域级数据查询
  time_slice.py             # 时间切片查询
  technical.py              # 基础技术指标
  technical_deep.py         # 深度技术指标分析
  features.py               # 标准化特征
  cross_asset.py            # 跨资产分析
  cross_asset_history.py    # 跨资产历史序列
  risk.py                   # 风险指标
  portfolio_analytics.py    # 组合风险分析
  signals.py                # 交易信号
  sentiment.py              # 新闻情感
  news_intel.py             # 新闻情报
  macro.py                  # 宏观上下文
  overview.py               # 市场总览
  screener.py               # 资产筛选
  market_info.py            # 市场信息
  catalogs.py               # 目录查询
  data_quality.py           # 数据质量
  alternative.py            # 另类数据
  analytics_ts.py           # 分析时序
  aggregate.py              # 聚合端点
  exchange.py               # 交易所数据
  strategy.py               # 策略端点
  monitor.py                # 监控端点
  onchain.py                # 链上数据
  derivatives.py            # 衍生品数据
  orderflow.py              # 订单流
  ai_context.py             # AI 上下文
  microstructure.py         # 微观结构
  factor_explorer.py        # 因子探索
  social_sentiment.py       # 社交情绪
  whale_tracker.py          # 巨鲸追踪
  orderflow_micro.py        # 微观订单流
  defi.py                   # DeFi 协议
  bridge_flow.py            # 跨链桥流
  regulatory.py             # 监管动态
  regime.py                 # 市场状态
  anomaly.py                # 异常检测
  liquidity.py              # 流动性分析
  volatility.py             # 波动率预测
  etf_flow.py               # ETF 资金流
  basis_curve.py            # 期货期限结构
  mev.py                    # MEV 数据
  cefi_lending.py           # CeFi 借贷利率
  temporal_pattern.py       # 时间模式
  flow_decomposition.py     # 资金流分解
  contagion_risk.py         # 传染风险
  alpha_decay.py            # 信号衰减
  narrative_regime.py       # 叙事状态机
  perpetual_dex.py            # 永续 DEX
  onchain_address.py          # 链上地址画像
  dex_liquidity.py            # DEX 流动性
  gas_network.py              # Gas/网络
  governance.py               # 治理投票
  liquidation_cascade.py      # 清算级联
  cross_venue_arb.py          # 跨所套利
  onchain_lead_lag.py         # 链上领先滞后
  prediction_market.py        # 预测市场
  onchain_holder.py           # 链上持有者
  liquid_staking.py           # 流动性质押
  mempool.py                  # 内存池
  funding_round.py            # VC 融资
  exchange_reserve.py         # 交易所储备
  miner.py                    # 矿工数据
  derivatives_sentiment.py    # 衍生品情绪
  holder_behavior.py          # 持有者行为
  liquidity_regime.py         # 流动性 Regime
  event_probability.py        # 事件概率
  miner_pressure.py           # 矿工压力
  sentiment_composite.py      # 综合情绪
  stablecoin_flow.py          # 稳定币事件流
  token_unlock.py             # 代币解锁
  orderbook_depth.py          # 盘口深度
  whale_pnl.py                # 巨鲸 PnL
  nft_market.py               # NFT 市场
  defi_liquidation.py         # DeFi 清算
  dex_trade_flow.py           # DEX 交易流
  cross_chain_msg.py          # 跨链消息
  lending_utilization.py      # 借贷利用率
  search_trend.py             # 搜索趋势
  exchange_announcement.py    # 交易所公告
  stablecoin_pulse.py         # 稳定币脉冲
  unlock_impact.py            # 解锁冲击
  depth_regime.py             # 深度 Regime
  smart_money_conviction.py   # Smart Money 信念
  defi_stress.py              # DeFi 压力
  retail_fomo.py              # 散户 FOMO
```

## 路由注册

所有路由在 `api/app.py` 中通过 `app.include_router()` 注册，每个路由带有独立的 `prefix` 和 `tags`。

## 设计原则

- 每个路由文件只做参数校验和响应格式化
- 业务逻辑下沉到 `logic_layer` 或直接查询数据库
- 共享的符号归一化、DB 获取等逻辑放在 `_helpers.py`
- 所有端点返回 JSON，字段命名使用 snake_case

## 性能优化

- `aggregate.py` 的 `multi_asset_compare`、`sector_snapshot`、`derivatives_heatmap` 端点使用 `WHERE symbol IN (...)` 批量查询替代逐 symbol 循环查询，避免 N+1 查询问题
- 批量查询后在 Python 侧按 symbol 分组，查询次数从 O(N) 降低到 O(1)
