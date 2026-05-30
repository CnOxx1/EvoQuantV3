# taker_flow

## 当前职责

- 输出 `aggressive_buy_notional`
- 输出 `aggressive_sell_notional`
- 输出 `net_taker_notional`
- 输出 `cvd`

## 存储语义

当前与 `trades` 共用 `trade_flow_bars` 存储。

## 读取约束

读取时必须结合 `market_type` 判断语义：

- `spot`：现货主动买卖流
- `linear_swap`：线性合约主动买卖流
