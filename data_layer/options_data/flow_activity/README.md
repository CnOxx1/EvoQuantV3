# flow_activity 子模块

`flow_activity` 负责把期权增量成交、开仓意图和 block tape 转换成 AI 能直接读取的结构化证据。

## 当前职责

- 输出 `call buyer premium share`
- 输出 `put buyer premium share`
- 输出 `net call / net put premium flow ratio`
- 输出 `opening flow share`
- 输出 `near expiry flow share`
- 输出 `block trade flow share`

## 当前输出因子

- `options_call_buyer_premium_share`
- `options_put_buyer_premium_share`
- `options_net_call_premium_flow_ratio`
- `options_net_put_premium_flow_ratio`
- `options_opening_flow_share`
- `options_near_expiry_flow_share`
- `options_block_trade_flow_share`

## 为什么这层重要

如果没有这类数据，AI 很难回答下面这些交易上非常实际的问题：

- 今天新增期权需求更偏向追涨 call 还是买保护 put
- 当前 tape 主要是新开仓，还是更多是换手和平仓
- 短端近到期成交是否突然放大
- 当前是否出现明显的机构 block flow

## 数据来源

当前 collector 已接入 Deribit 公开 API（`https://www.deribit.com/api/v2/public/`）作为免费 fallback 数据源。通过 `get_last_trades_by_currency` 获取最近期权成交记录，按 call/put 类型和 buyer/seller initiated 分类聚合计算 premium flow 和 opening/block flow share。

限制：Deribit 免费 API 仅覆盖 BTC/ETH，SOL/SUI 等资产需要付费数据源补充。

## 维护重点

- `positioning` 是存量 OI 结构，`flow_activity` 是增量成交意图，二者不能混用
- buyer-initiated 与 seller-initiated premium 的口径必须稳定，否则 `net flow ratio` 会失真
- `block trade share` 反映的是交易类型，不代表方向，不能直接当成 bullish / bearish 标签
- 如果需要按 `7d / 30d / 90d+` 拆 premium flow，应放到 `expiry_structure` 单独维护
- 如果上游把 premium 单位从名义金额改成权利金金额，必须同步更新这里和模块总 README
