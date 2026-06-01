# flow_decomposition — 资金流分解模块

## 定位

将市场订单流分解为不同参与者类型的资金流向，识别聪明钱与散户行为差异。通过 VPIN 等指标量化信息不对称程度，为 AI 提供闪崩预警和资金方向判断。

## 计算逻辑

| 类型 | 计算方法 | 说明 |
|---|---|---|
| VPIN | 按 bucket 分组计算买卖不平衡 | 量化知情交易概率 |
| smart_money | 大单 + 低波动时段识别 | 聪明钱方向判断 |
| retail_flow | 小单 + 高波动时段识别 | 散户行为识别 |
| accumulation | 价格横盘 + 持续买入 | 积累阶段判定 |
| distribution | 价格高位 + 持续卖出 | 派发阶段判定 |

## 代码结构

```
flow_decomposition/
├── __init__.py          # 包入口
├── calculator.py        # 资金流计算器
├── models.py            # 数据模型
├── repository.py        # 数据访问层
├── service.py           # 服务层
├── runner.py            # CLI 入口
└── README.md
```

## 数据表

### flow_decomposition

| 字段 | 类型 | 说明 |
|---|---|---|
| ts | TIMESTAMP | 计算时间戳 |
| symbol | TEXT | 交易对 |
| vpin | REAL | VPIN 值 |
| informed_flow_ratio | REAL | 知情交易占比 |
| retail_flow_ratio | REAL | 散户交易占比 |
| smart_money_direction | TEXT | 聪明钱方向 |
| accumulation_phase | REAL | 积累阶段概率 |
| distribution_phase | REAL | 派发阶段概率 |

### vpin_history

| 字段 | 类型 | 说明 |
|---|---|---|
| ts | TIMESTAMP | 计算时间戳 |
| symbol | TEXT | 交易对 |
| vpin_value | REAL | VPIN 值 |
| vpin_percentile | REAL | VPIN 历史分位 |
| alert_level | TEXT | 告警等级 |

## 运行方式

```bash
# 执行资金流分解
python -m logic_layer.flow_decomposition.runner --mode calculate

# 指定标的和时间窗口
python -m logic_layer.flow_decomposition.runner --mode calculate --symbols BTC,ETH --hours 24

# 输出 AI 上下文
python -m logic_layer.flow_decomposition.runner --print-context
```

## AI 上下文 Bundle 格式

```json
{
  "status": "ready",
  "as_of": "2025-01-15T08:00:00",
  "vpin_level": {
    "BTC": {"vpin": 0.72, "percentile": 85, "alert": "warning"},
    "ETH": {"vpin": 0.45, "percentile": 50, "alert": "normal"}
  },
  "smart_money_direction": {
    "BTC": "accumulating",
    "ETH": "neutral"
  },
  "flash_crash_risk": {
    "level": "elevated",
    "reason": "VPIN > 0.7 on BTC, approaching critical threshold 0.8"
  }
}
```

## 输入依赖

- `orderflow_data` 表（订单流数据）
- `whale_tracker` 表（大户追踪数据）
