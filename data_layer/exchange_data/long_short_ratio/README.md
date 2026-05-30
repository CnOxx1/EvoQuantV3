# long_short_ratio

## 当前职责

- 采集 `long_ratio`
- 采集 `short_ratio`
- 采集 `long_short_ratio`
- 采集 `top_trader_long_ratio`
- 采集 `top_trader_short_ratio`

## 目标

让 AI 看见多空拥挤结构，而不是只看 funding。

## 当前实现

- 数据源：通过 ccxt `fetch_long_short_ratio_history()` 从 Binance / OKX / Bybit 获取
- 时间粒度：1h
- 回溯窗口：默认 48 小时
- 覆盖范围：TARGET_SYMBOLS × TARGET_EXCHANGES
- 去重：基于 `(symbol, exchange, timestamp)` 唯一约束
- 依赖：`ExchangeClientManager`（复用模块级 ccxt 实例管理）
- 注意：top_trader 字段依赖交易所是否返回，部分交易所可能只返回全局 ratio

## 当前约束

- 上游 `timestamp` 会统一标准化成 UTC-naive
- 如果 `timestamp` 缺失或损坏，会直接跳过该行，避免把低频背景站位误写成最新切片
- 即使 source 级通过 AI-ready，bundle 仍会继续做行级过滤；只给出单边账户比例或单边大户比例的真实行只会保留在 `raw_positioning`
