# relative_value 子模块

`relative_value` 负责回答一个更接近交易的问题：当前期权隐含波动率到底只是高，还是已经高于真实波动很多。

## 当前职责

- 输出 `7d / 30d realized vol`
- 输出 `7d / 30d IV-RV spread`

## 当前输出因子

- `options_realized_vol_7d`
- `options_realized_vol_30d`
- `options_iv_rv_spread_7d`
- `options_iv_rv_spread_30d`

## 为什么这层重要

如果只有 IV，而没有 realized vol，AI 只能知道“市场预期波动高”。

但交易更关心的是：

- 期权现在是不是已经被买得太贵
- 市场是否在为并不存在的波动支付过高溢价
- 哪些资产的短端 / 中端 IV 相对真实波动更拥挤

## 数据来源

当前 collector 已接入 Deribit 公开 API（`https://www.deribit.com/api/v2/public/`）作为免费 fallback 数据源。通过 `get_historical_volatility` 端点获取 realized vol，结合 `get_book_summary_by_currency` 的 ATM IV 计算 IV-RV spread。

限制：Deribit 免费 API 仅覆盖 BTC/ETH，SOL/SUI 等资产需要付费数据源补充。

## 维护重点

- `IV-RV spread` 的输入口径必须稳定
- 如果 realized vol 计算窗口变化，必须同步更新文档和因子语义
- 如果以后增加 `IV-RV ratio`，要用新 factor，不要复用现有 spread
