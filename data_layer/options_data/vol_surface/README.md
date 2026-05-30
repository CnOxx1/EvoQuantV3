# vol_surface 子模块

`vol_surface` 负责把标准化后的期权曲面快照转换成 AI 可直接消费的波动率因子。

## 当前职责

- 读取 `7d / 30d` ATM IV
- 计算 `7d - 30d` term structure
- 提取 `30d 25d risk reversal`
- 提取 `30d 25d butterfly`

## 当前输出因子

- `options_atm_iv_7d`
- `options_atm_iv_30d`
- `options_iv_term_structure_7d_30d`
- `options_25d_risk_reversal_30d`
- `options_25d_butterfly_30d`

## 数据来源

当前 collector 已接入 Deribit 公开 API（`https://www.deribit.com/api/v2/public/`）作为免费 fallback 数据源，覆盖 BTC 和 ETH 期权。通过 `get_book_summary_by_currency` 端点获取各 instrument 的 IV，按 tenor 聚合计算 ATM IV 和 term structure。

限制：Deribit 免费 API 仅覆盖 BTC/ETH，SOL/SUI 等资产需要付费数据源补充。

## 维护重点

- 不要把这里写成交易所私有字段堆砌层
- 应该优先维护"标准化输入 contract"稳定
- 如果新增 tenor，优先用新的 factor，而不是复用旧 factor 改语义
