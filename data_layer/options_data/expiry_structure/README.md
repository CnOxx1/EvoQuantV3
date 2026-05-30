# expiry_structure 子模块

`expiry_structure` 负责把期权按到期桶拆分的 OI、gamma 和 premium flow 分布转换成 AI 能直接读取的结构化证据。

## 当前职责

- 输出 `7d / 30d / 90d+` 的 OI share
- 输出 `7d / 30d` 的 gamma share
- 输出 `7d / 30d` 的 premium flow share

## 当前输出因子

- `options_oi_share_7d`
- `options_oi_share_30d`
- `options_oi_share_90d_plus`
- `options_gamma_share_7d`
- `options_gamma_share_30d`
- `options_premium_flow_share_7d`
- `options_premium_flow_share_30d`

## 为什么这层重要

如果没有这类数据，AI 很难回答下面这些交易上非常实际的问题：

- 当前风险更集中在 `7d` 事件窗，还是 `30d` 月度窗
- 当前 gamma 是否主要堆在短端，从而放大短线被动对冲
- 当前 premium flow 是在追逐近端事件，还是在布局更长一点的到期窗
- 长端 `90d+` OI 是否明显堆积，意味着结构性仓位仍在场

## 数据来源

当前 collector 已接入 Deribit 公开 API（`https://www.deribit.com/api/v2/public/`）作为免费 fallback 数据源。通过 `get_book_summary_by_currency` 获取各 instrument 的 OI 和 greeks，按到期日分桶聚合计算 OI share、gamma share 和 premium flow share。

限制：Deribit 免费 API 仅覆盖 BTC/ETH，SOL/SUI 等资产需要付费数据源补充。

## 维护重点

- `expiry_structure` 是按到期桶拆分的横截面结构，不要和 `positioning` 的总量结构混用
- bucket 命名口径必须稳定，尤其是 `7d / 30d / 90d+`
- `gamma share` 的分母必须使用统一的 `gross gamma`
- 如果未来把 bucket 粒度改得更细，必须同步更新这里和模块总 README
