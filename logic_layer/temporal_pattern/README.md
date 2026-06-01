# temporal_pattern — 时间模式识别模块

## 定位

识别市场中的时间维度规律性模式，包括日内季节性、月度效应和周期性事件影响。为 AI 提供时间维度的先验知识，辅助判断当前时段的历史偏向。

## 检测维度

| 类型 | 检测方法 | 说明 |
|---|---|---|
| intraday_seasonality | 按小时/星期聚合收益率 | 日内季节性模式 |
| monthly_effect | 月度收益率统计 | 月度效应识别 |
| halving_cycle | 减半周期相位计算 | 减半周期相位位置 |
| options_gravity | 期权到期日前后价格引力 | 期权到期引力效应 |
| funding_cycle | Funding 8h 周期分析 | 资金费率周期模式 |

## 代码结构

```
temporal_pattern/
├── __init__.py          # 包入口
├── calculator.py        # 时间模式计算器
├── models.py            # 数据模型
├── repository.py        # 数据访问层
├── service.py           # 服务层
├── runner.py            # CLI 入口
└── README.md
```

## 数据表

### temporal_patterns

| 字段 | 类型 | 说明 |
|---|---|---|
| ts | TIMESTAMP | 检测时间戳 |
| symbol | TEXT | 交易对 |
| pattern_type | TEXT | 模式类型 |
| pattern_value | REAL | 模式值 |
| confidence | REAL | 置信度 |
| historical_avg | REAL | 历史均值 |
| current_deviation | REAL | 当前偏离度 |

### seasonal_profiles

| 字段 | 类型 | 说明 |
|---|---|---|
| symbol | TEXT | 交易对 |
| dimension | TEXT | 维度 |
| hour_of_day | INTEGER | 小时 |
| day_of_week | INTEGER | 星期 |
| month | INTEGER | 月份 |
| avg_value | REAL | 均值 |
| std_value | REAL | 标准差 |
| sample_count | INTEGER | 样本数 |

## 运行方式

```bash
# 执行时间模式识别
python -m logic_layer.temporal_pattern.runner --mode detect

# 指定标的和时间窗口
python -m logic_layer.temporal_pattern.runner --mode detect --symbols BTC,ETH --hours 24

# 输出 AI 上下文
python -m logic_layer.temporal_pattern.runner --print-context
```

## AI 上下文 Bundle 格式

```json
{
  "status": "ready",
  "as_of": "2025-01-15T08:00:00",
  "current_period_bias": {
    "hour_of_day": 14,
    "day_of_week": 3,
    "historical_return_avg": 0.0012,
    "historical_volatility_avg": 0.015
  },
  "upcoming_seasonal_events": [
    {"event": "options_expiry", "time": "2025-01-17T08:00:00", "expected_impact": "high"},
    {"event": "funding_settlement", "time": "2025-01-15T16:00:00", "expected_impact": "medium"}
  ],
  "cycle_phase": {
    "halving_cycle_phase": 0.65,
    "funding_cycle_phase": 0.3
  }
}
```

## 输入依赖

- `merged_klines` 表（价格和成交量）
- `funding_rates` 表（资金费率）
