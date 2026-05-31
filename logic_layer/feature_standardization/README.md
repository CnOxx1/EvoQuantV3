# 特征标准化模块 `feature_standardization`

## 模块定位

`feature_standardization` 属于逻辑处理层，负责对 `technical_indicators` 输出的原始特征进行滚动标准化，生成 Z-Score、百分位和跨资产排名，供 AI 直接消费。

原始技术指标的量纲和分布差异很大（RSI 是 0-100，ATR 是绝对价格单位），直接喂给 AI 会导致特征权重失衡。这个模块解决的就是这个问题。

## 模块代码树

```text
logic_layer/feature_standardization/
  __init__.py       # 包入口
  registry.py       # 特征注册表：哪些特征需要标准化、用什么方法
  calculator.py     # 标准化计算引擎
  models.py         # 数据模型定义
  repository.py     # 数据读取与结果落库
  service.py        # 编排入口
  runner.py         # CLI 运行入口
```

## 标准化计算公式

### Rolling Z-Score

```
Z(t) = (x(t) - μ_rolling) / σ_rolling
```

- `μ_rolling = mean(x, window)`
- `σ_rolling = std(x, window, ddof=0)`
- `min_periods = window / 4`（允许窗口未满时提前输出）
- 当 `σ_rolling = 0` 时输出 NaN

提供两个窗口：
- `zscore_7d`：window = 168（7 × 24 小时 bars）
- `zscore_30d`：window = 720（30 × 24 小时 bars）

### Rolling Percentile Rank

```
Percentile(t) = count(x_window < x(t)) / (len(x_window) - 1) × 100
```

- 输出范围：0 ~ 100
- `min_periods = window / 4`
- 当前只使用 30 天窗口：`percentile_30d`

### Cross-Asset Rank

```
Rank(symbol) = 按特征值在所有资产中的排序位置
```

- rank 1 = 最强/最极端（默认降序）
- 对于反向指标（如 Williams %R），使用升序排名
- 空值资产不参与排名

### Regime 分类

将 Z-Score 映射为语义标签：

| Z-Score 区间 | 标签 | 含义 |
| --- | --- | --- |
| z ≥ 2.0 | `extreme_high` | 极端偏高 |
| 1.0 ≤ z < 2.0 | `elevated` | 偏高 |
| -1.0 ≤ z < 1.0 | `normal` | 正常区间 |
| -2.0 ≤ z < -1.0 | `depressed` | 偏低 |
| z < -2.0 | `extreme_low` | 极端偏低 |

### 复合维度评分

```
Composite = mean(非空组件的 Z-Score)
```

将同类别多个特征的标准化值取均值，得到维度级别的综合评分。

### 置信度

```
Confidence = available_count / required_count
```

| 比率 | 置信度 |
| --- | --- |
| ≥ 80% | `high` |
| ≥ 50% | `medium` |
| < 50% | `low` |

## 特征注册表

当前注册了 **28 个特征**，分为 5 个复合维度和 7 个独立特征：

### Momentum 维度（8 个）

| 特征名 | 数据源列 | 反向 | 说明 |
| --- | --- | --- | --- |
| `rsi_14` | rsi_14 | 否 | 14 周期 RSI |
| `rsi_28` | rsi_28 | 否 | 28 周期 RSI |
| `macd_histogram` | macd_histogram | 否 | MACD 柱状图 |
| `roc_12` | roc_12 | 否 | 12 周期变化率 |
| `cci_20` | cci_20 | 否 | 20 周期 CCI |
| `williams_r_14` | williams_r_14 | 是 | Williams %R（反向：越低越超买） |
| `stoch_rsi_k_14` | stoch_rsi_k_14 | 否 | 随机 RSI K 线 |
| `tsi_line` | tsi_line | 否 | TSI 主线 |

复合评分 = `mean(rsi_14_z, rsi_28_z, macd_z, roc_z, cci_z, -williams_r_z, stoch_rsi_z, tsi_z)`

### Volatility 维度（5 个）

| 特征名 | 数据源列 | 说明 |
| --- | --- | --- |
| `atr_pct_14` | atr_pct_14 | ATR 百分比 |
| `bb_width` | bb_width | 布林带宽度 |
| `historical_volatility_20` | historical_volatility_20 | 历史波动率 |
| `keltner_width_20` | keltner_width_20 | Keltner 通道宽度 |
| `chaikin_volatility_10` | chaikin_volatility_10 | Chaikin 波动率 |

复合评分 = `mean(atr_z, bb_z, hv_z, keltner_z, chaikin_z)`

### Leverage 维度（2 个）

| 特征名 | 数据源列 | 说明 |
| --- | --- | --- |
| `funding_rate_mean` | funding_rate_mean | 资金费率均值 |
| `funding_rate_std` | funding_rate_std | 资金费率标准差 |

复合评分 = `mean(funding_mean_z, funding_std_z)`

### Flow 维度（5 个）

| 特征名 | 数据源列 | 说明 |
| --- | --- | --- |
| `obv_slope_20` | obv_slope_20 | OBV 斜率 |
| `cmf_20` | cmf_20 | Chaikin 资金流 |
| `volume_zscore_20` | volume_zscore_20 | 成交量 Z-Score |
| `force_index_13` | force_index_13 | 力度指数 |
| `pvo_line` | pvo_line | PVO 主线 |

复合评分 = `mean(obv_z, cmf_z, vol_z, force_z, pvo_z)`

### 独立特征（7 个）

| 特征名 | 数据源列 | 说明 |
| --- | --- | --- |
| `adx_14` | adx_14 | 趋势强度 |
| `linear_reg_r2_20` | linear_reg_r2_20 | 线性回归 R² |
| `sharpe_like_20` | sharpe_like_20 | 类 Sharpe 比率 |
| `sortino_like_20` | sortino_like_20 | 类 Sortino 比率 |
| `return_skew_20` | return_skew_20 | 收益偏度 |
| `orderbook_depth_imbalance_mean` | orderbook_depth_imbalance_mean | 盘口深度不平衡 |
| `orderbook_spread_bps_mean` | orderbook_spread_bps_mean | 盘口价差 bps |

这些特征只输出标准化值，不参与复合维度计算。

## 每个特征的标准化输出

对每个注册特征，模块输出：

- `{feature}_zscore_7d` — 7 天滚动 Z-Score
- `{feature}_zscore_30d` — 30 天滚动 Z-Score
- `{feature}_percentile_30d` — 30 天滚动百分位
- `{feature}_cross_rank` — 跨资产排名
- `{feature}_regime` — 基于 zscore_30d 的 Regime 标签

## 运行方式

```bash
python -m logic_layer.feature_standardization.runner
```
