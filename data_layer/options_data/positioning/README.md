# positioning 子模块

`positioning` 负责把期权 OI 分布转换成 AI 能直接理解的仓位结构因子。

## 当前职责

- 计算 `30d put/call OI ratio`
- 计算 `30d call OI share`
- 输出 `30d total OI notional`
- 计算 `near expiry OI share`
- 计算 `largest expiry OI share`

## 当前输出因子

- `options_put_call_oi_ratio_30d`
- `options_call_oi_share_30d`
- `options_total_oi_notional_30d`
- `options_near_expiry_oi_share`
- `options_largest_expiry_oi_share`

## 数据来源

当前 collector 已接入 Deribit 公开 API（`https://www.deribit.com/api/v2/public/`）作为免费 fallback 数据源，覆盖 BTC 和 ETH 期权。通过 `get_book_summary_by_currency` 端点获取各 instrument 的 OI，按 put/call 类型聚合计算仓位结构因子。

限制：Deribit 免费 API 仅覆盖 BTC/ETH，SOL/SUI 等资产需要付费数据源补充。

## 维护重点

- 近到期集中度和单一到期集中度不要混用
- OI 结构因子不要和 `strike_concentration` / `gamma_exposure` 的墙位、gamma 因子混用
- `positioning` 描述存量仓位结构，不要和 `flow_activity` 的增量成交意图混用
- `positioning` 是总量结构，不要和 `expiry_structure` 的按到期桶拆分结构混用
- 如果总 OI 的统计口径变了，必须同步更新模块文档和上游 contract
