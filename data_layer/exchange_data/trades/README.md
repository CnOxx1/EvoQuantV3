# trades

## 当前职责

负责采集最近成交明细并聚合为 `trade_flow_bars`。

当前会同时尝试采集：

- 现货逐笔成交
- 线性合约逐笔成交

## 存储语义

两类数据统一写入同一张表，但用 `market_type` 区分：

- `spot`
- `linear_swap`

当前同时为 `taker_flow` 提供底层数据，不再重复抓取同一批成交。

## 当前数据质量约束

- `trade_flow` 不会再把 `side` 缺失的成交默认当成 `sell`
- `trade_flow` 不会再把缺失 `price / amount / cost` 的成交默认当成 `0` 成交额
- 只有同时具备可判定方向 `buy / sell`，且可推导成交额的真实成交，才会进入 bar 聚合
- 如果某个 bar 里没有任何可用成交，这个 bar 会被直接跳过，而不是伪装成“零主动买卖压力”
- `raw_payload_json` 会保留原始成交列表，并补充：
  - `raw_trade_count`
  - `usable_trade_count`
  - `excluded_trade_count`
  - `excluded_missing_side_count`
  - `excluded_missing_notional_count`

## 结果说明

这意味着下游 AI 读到的 `trade_flow_bars` 至少不再混入“由缺字段硬算出来的假卖压或假零成交额”。
