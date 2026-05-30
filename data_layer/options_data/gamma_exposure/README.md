# gamma_exposure 子模块

`gamma_exposure` 负责把期权 dealer gamma regime 转换成 AI 能直接读取的结构化证据。

## 当前职责

- 输出 `net gamma exposure` 原始规模
- 输出 `net gamma / gross gamma` 的有符号比例
- 输出 `gamma flip` 相对现货的距离
- 输出 `call gamma wall / put gamma wall` 相对现货的距离
- 输出单一最大 gamma strike 的集中度
- 输出近到期 gamma 集中度

## 当前输出因子

- `options_net_gamma_exposure`
- `options_net_gamma_exposure_ratio`
- `options_gamma_flip_distance_pct`
- `options_call_gamma_wall_distance_pct`
- `options_put_gamma_wall_distance_pct`
- `options_top_gamma_strike_share`
- `options_near_expiry_gamma_share`

## 为什么这层重要

如果没有这类数据，AI 很难回答下面这些交易上非常实际的问题：

- 当前市场更偏 `long gamma` 还是 `short gamma`
- 现价离 `gamma flip` 还有多远
- 上下方最近的 `gamma wall` 在哪里
- 近到期 gamma 是否过度集中，导致价格波动被被动对冲放大

## 数据来源

当前 collector 已接入 Deribit 公开 API（`https://www.deribit.com/api/v2/public/`）作为免费 fallback 数据源。通过 `get_book_summary_by_currency` 获取各 instrument 的 OI 和 greeks，结合 `get_index_price` 现货价格计算 gamma exposure 和 flip/wall 距离。

限制：Deribit 免费 API 仅覆盖 BTC/ETH，SOL/SUI 等资产需要付费数据源补充。

## 维护重点

- `net gamma exposure` 和 `net gamma exposure ratio` 要同时保留，前者看规模，后者看 regime 强弱
- 距离类指标必须保留有符号方向，不要改成绝对值
- `gamma wall` 与 `OI wall` 语义不同，不能和 `strike_concentration` 混用
- 如果需要按 `7d / 30d / 90d+` 拆 gamma 分布，应放到 `expiry_structure` 单独维护
- 如果需要补 `vanna / charm` 这类动态对冲压力，应放到 `hedge_pressure` 单独维护
- 如果上游更改 `gross gamma` 统计口径，必须同步更新这里和模块总 README
