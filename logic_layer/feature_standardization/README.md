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

## 标准化方法

| 方法 | 说明 | 适用场景 |
| --- | --- | --- |
| Z-Score | `(x - mean) / std` | 近似正态分布的特征 |
| Percentile | 滚动窗口内百分位 | 有界或偏态分布的特征 |
| Cross-Rank | 同一时刻跨资产排名 | 相对强弱比较 |

## 滚动窗口

- 7 天窗口：短期标准化，捕捉近期状态变化
- 30 天窗口：中期标准化，提供更稳定的基准

每个窗口有最小样本数要求，样本不足时输出空值。

## 复合维度

`registry.py` 中的 `COMPOSITE_DEFINITIONS` 定义了多个特征组合成的复合维度评分，例如趋势强度、动量质量等。

## 运行方式

```bash
python -m logic_layer.feature_standardization.runner
```
