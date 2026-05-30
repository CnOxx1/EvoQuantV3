# hedge_pressure 子模块

`hedge_pressure` 负责把期权 dealer 的动态对冲压力转换成 AI 能直接读取的结构化证据。

## 当前职责

- 输出 `vanna exposure / vanna exposure ratio`
- 输出 `charm exposure / charm exposure ratio`
- 输出 `volga exposure / volga exposure ratio`
- 输出 `vomma exposure / vomma exposure ratio`
- 输出 `color exposure / color exposure ratio`
- 输出 `vanna flip / charm flip` 相对现货的距离
- 输出 `near expiry charm share`
- 输出 `near expiry color share`

## 当前输出因子

- `options_vanna_exposure`
- `options_vanna_exposure_ratio`
- `options_charm_exposure`
- `options_charm_exposure_ratio`
- `options_vanna_flip_distance_pct`
- `options_charm_flip_distance_pct`
- `options_near_expiry_charm_share`
- `options_volga_exposure`
- `options_volga_exposure_ratio`
- `options_vomma_exposure`
- `options_vomma_exposure_ratio`
- `options_color_exposure`
- `options_color_exposure_ratio`
- `options_near_expiry_color_share`

## 为什么这层重要

如果没有这类数据，AI 很难回答下面这些交易上非常实际的问题：

- 波动率上升或下降时，dealer 对冲会不会把价格推得更快
- 波动率出现二阶凸性冲击时，dealer 会不会出现二次被动对冲放大
- 随着时间流逝，短端 charm 会不会逼出同向被动对冲
- gamma 随时间衰减时，近到期 color 会不会把路径推向更脆弱的状态
- 当前更接近 `vanna flip` 还是 `charm flip`
- 近到期 charm / color 是否过度集中，导致临近到期的路径依赖风险上升

## 数据来源

当前 collector 已接入 Deribit 公开 API（`https://www.deribit.com/api/v2/public/`）作为免费 fallback 数据源。通过 `get_book_summary_by_currency` 获取各 instrument 的 greeks 和 OI，结合 `get_index_price` 现货价格计算 vanna/charm/volga/vomma/color exposure 和 flip 距离。

限制：Deribit 免费 API 仅覆盖 BTC/ETH，SOL/SUI 等资产需要付费数据源补充。

## 维护重点

- `hedge_pressure` 是动态 greek 压力，不要和 `gamma_exposure` 的静态 gamma regime 混用
- `vanna / charm ratio` 的分母口径必须稳定，建议统一相对 `gross gamma`
- `volga / vomma / color ratio` 当前也统一相对 `gross gamma`，不要混入其他 vendor 私有分母
- flip distance 必须保留有符号方向，不要改成绝对值
- `volga` 和 `vomma` 在不同 vendor 里可能是同义词，也可能是不同口径；上游标准化时必须显式确认，不能在 collector 里擅自互相复制
- `near expiry color share` 的分母应优先使用 `total_color_exposure` 或等价总量字段，避免把净值误当作集中度口径
- 未来如果继续扩展，应优先补按 expiry bucket 分层的 `vanna / volga / color`
