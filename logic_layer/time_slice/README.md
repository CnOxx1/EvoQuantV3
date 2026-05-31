# 时间切片查询模块 `time_slice`

## 模块定位

`time_slice` 是一个纯只读查询模块，提供任意历史时刻的全市场特征快照。

它不采集数据、不做计算、不写入数据库，只负责从已有的 10 个域表中按时间点聚合出完整的市场状态切片。

## 模块代码树

```text
logic_layer/time_slice/
  __init__.py       # 包入口
  models.py         # 数据模型定义（TimeSlice, DomainSlice, FeatureHistory）
  repository.py     # 各域数据读取
  service.py        # 查询编排入口
  runner.py         # CLI 运行入口
```

## 覆盖域

| 域 | 数据来源 | Staleness 阈值 |
| --- | --- | --- |
| `klines` | merged_klines | 1h |
| `technical_indicators` | technical_indicators | 1h |
| `feature_standardization` | feature_standardization_* | 2h |
| `cross_asset` | cross_asset_* | 2h |
| `portfolio_risk` | portfolio_risk_* | 2h |
| `macro_context` | macro_context_snapshots | 24h |
| `market_breadth` | market_breadth_snapshots | 2h |
| `asset_readiness` | asset_readiness_snapshots | 2h |
| `ai_market_context` | ai_market_context_* | 2h |
| `exchange_comparison` | exchange_comparison_* | 1h |

## 核心接口

- `get_slice_at(timestamp, symbol)` — 获取指定时刻的全域特征快照
- 每个域的数据会标记 `freshness_status`（fresh / stale / missing）
