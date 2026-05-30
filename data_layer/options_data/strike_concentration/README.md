# strike_concentration 子模块

`strike_concentration` 负责把期权行权价墙位和 pinning 风险转换成 AI 能直接读取的结构化证据。

## 当前职责

- 输出 `max pain` 相对现货的距离
- 输出 `call wall / put wall` 相对现货的距离
- 输出单一最大行权价的 OI 集中度
- 输出近到期最大行权价的 OI 集中度
- 输出 ATM 附近行权价带的 OI 集中度

## 当前输出因子

- `options_max_pain_distance_pct`
- `options_call_wall_distance_pct`
- `options_put_wall_distance_pct`
- `options_top_strike_oi_share`
- `options_near_expiry_top_strike_oi_share`
- `options_atm_strike_oi_share`

## 为什么这层重要

如果没有这类数据，AI 很难回答下面这些交易上非常实际的问题：

- 当前价格是否正在向 `max pain` 区域回归
- 上方 / 下方最近的大墙位离现价有多远
- 单一 strike 是否已经出现过度拥挤
- 近到期是否存在 pinning 风险或突破后被动对冲放大风险

## 数据来源

当前 collector 已接入 Deribit 公开 API（`https://www.deribit.com/api/v2/public/`）作为免费 fallback 数据源。通过 `get_book_summary_by_currency` 获取各 instrument 的 OI 分布，结合 `get_index_price` 现货价格计算 max pain、call/put wall 距离和行权价集中度。

限制：Deribit 免费 API 仅覆盖 BTC/ETH，SOL/SUI 等资产需要付费数据源补充。

## 维护重点

- 距离类指标必须保留有符号方向，不要改成绝对值
- `OI wall` 和 `gamma wall` 语义不同，要和 `gamma_exposure` 子模块分开维护
- `top strike share` 和 `near expiry top strike share` 不能混用
