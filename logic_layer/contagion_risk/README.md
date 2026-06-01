# contagion_risk — 传染风险建模模块

## 定位

建模加密市场中的系统性风险传染路径，量化极端事件下资产间的风险溢出效应。为 AI 提供系统性风险评估和级联崩溃预警。

## 计算逻辑

| 类型 | 计算方法 | 说明 |
|---|---|---|
| conditional_correlation | 下跌 >2σ 时的条件相关性 | 极端行情下的相关性变化 |
| CoVaR | 5% 尾部条件风险价值 | 系统性风险贡献度 |
| tail_beta | 极端下跌时的 Beta 放大 | 尾部风险放大倍数 |
| stablecoin_depeg | 稳定币脱锚概率建模 | 稳定币健康状态评估 |

## 代码结构

```
contagion_risk/
├── __init__.py          # 包入口
├── calculator.py        # 传染风险计算器
├── models.py            # 数据模型
├── repository.py        # 数据访问层
├── service.py           # 服务层
├── runner.py            # CLI 入口
└── README.md
```

## 数据表

### contagion_metrics

| 字段 | 类型 | 说明 |
|---|---|---|
| ts | TIMESTAMP | 计算时间戳 |
| symbol | TEXT | 交易对 |
| covar_95 | REAL | 95% CoVaR |
| conditional_correlation | REAL | 条件相关性 |
| tail_beta | REAL | 尾部 Beta |
| systemic_contribution | REAL | 系统性风险贡献度 |

### cascade_risk

| 字段 | 类型 | 说明 |
|---|---|---|
| ts | TIMESTAMP | 计算时间戳 |
| risk_type | TEXT | 风险类型 |
| risk_level | TEXT | 风险等级 |
| affected_assets | TEXT | 受影响资产 |
| trigger_conditions | TEXT | 触发条件 |

## 运行方式

```bash
# 执行传染风险建模
python -m logic_layer.contagion_risk.runner --mode calculate

# 指定标的和时间窗口
python -m logic_layer.contagion_risk.runner --mode calculate --symbols BTC,ETH --hours 24

# 输出 AI 上下文
python -m logic_layer.contagion_risk.runner --print-context
```

## AI 上下文 Bundle 格式

```json
{
  "status": "ready",
  "as_of": "2025-01-15T08:00:00",
  "systemic_risk_score": 72,
  "max_contagion_path": ["LUNA_depeg", "UST_cascade", "BTC_liquidation"],
  "tail_risk_amplification": {
    "BTC": 1.8,
    "ETH": 2.3,
    "SOL": 3.1
  },
  "stablecoin_health": {
    "USDT": {"depeg_probability": 0.02, "status": "healthy"},
    "USDC": {"depeg_probability": 0.01, "status": "healthy"}
  }
}
```

## 输入依赖

- `cross_asset` 表（跨资产数据）
- `onchain` 表（链上数据）
- `defi_protocol` 表（DeFi 协议数据）
