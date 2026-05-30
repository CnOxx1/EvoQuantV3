# liquidations

## 当前职责

- 采集 `long_liquidation_notional`
- 采集 `short_liquidation_notional`
- 采集 `total_liquidation_notional`

## 目标

让 AI 识别逼空、踩踏和异常挤仓。

## 当前实现

- 数据源：通过 ccxt `fetch_liquidations()` 从 Binance / OKX / Bybit 获取
- 聚合方式：按 5 分钟窗口聚合，分 long/short 累加 notional
- 覆盖范围：TARGET_SYMBOLS × TARGET_EXCHANGES（与 exchange_data 模块一致）
- 回溯窗口：默认 1 小时
- 去重：基于 `(symbol, exchange, open_time)` 唯一约束
- 依赖：`ExchangeClientManager`（复用模块级 ccxt 实例管理）

## 当前约束

- 上游 `open_time` 会统一标准化成 UTC-naive
- 如果 `open_time` 缺失或损坏，会直接跳过该 bar，不会伪装成当前最新清算压力
- 缺失的清算字段不会再被强制写成 `0`
- 只有下面两类真实行才会进入 AI 可见的 `liquidations`
  - 显式给出 `total_liquidation_notional`
  - 或者同时给出 `long_liquidation_notional` 与 `short_liquidation_notional`
- 如果真实行完全缺少核心清算字段，会只保留在 `raw_liquidations`，并标记 `liquidations_missing_metrics`
- 如果真实行只给出部分清算字段，会只保留在 `raw_liquidations`，并标记 `liquidations_incomplete_metrics_present`
- 明确返回的全零清算值会继续保留，因为“零清算压力”本身也可能是真实市场状态

## 面向 AI 的输出语义

- `liquidations`
  - 只包含 source 级通过 AI-ready，且行级语义也足够完整的真实清算快照
- `raw_liquidations`
  - 保留所有真实已落库清算快照，供诊断和审计使用
- `liquidations_quality_summary`
  - 汇总 `visible_row_count / raw_row_count / missing_metric_count / incomplete_metric_count`
  - 用来告诉下游当前“没有清算压力”与“清算字段不完整”之间的区别

## 历史数据修复

- 如果数据库里还保留着旧版 collector 把未知字段写成 `0` 的污染行，可以执行：

```bash
python -m data_layer.exchange_data.runner --mode liquidations-repair
```

- 这个修复只依赖已落库的 `raw_payload_json`
- 原始 payload 明确给出的零值会保留
- 原始 payload 缺失的清算字段会恢复成 `NULL`
- 无法从 `raw_payload_json` 证明的字段不会被猜测性改写
