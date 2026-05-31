# 跨资产分析模块 `cross_asset_analysis`

## 模块定位

`cross_asset_analysis` 属于逻辑处理层，负责计算资产间的相关性矩阵、相对强弱、板块轮动和资金流向。

它是纯计算模块，不采集任何外部数据，只基于已有的价格序列进行跨资产统计分析。

## 模块代码树

```text
logic_layer/cross_asset_analysis/
  __init__.py       # 包入口
  models.py         # 数据模型定义
  calculator.py     # 纯计算引擎（不依赖数据库）
  repository.py     # 数据读取与结果落库
  service.py        # 编排入口
  runner.py         # CLI 运行入口
```

## 核心计算

| 计算项 | 方法 | 输出 |
| --- | --- | --- |
| 相关性矩阵 | Pearson 相关系数 | NxN 矩阵 |
| 相对强弱 | 收益率排名与 Z-Score | 各资产相对表现 |
| 板块轮动 | 板块收益率聚合与排名 | 板块动量评分 |
| 资金流向 | 成交量变化与价格协同 | 流入/流出方向 |

## 设计原则

- `calculator.py` 是纯函数，不依赖数据库，只接收对齐好的价格序列
- 所有序列必须等长且时间对齐后才传入计算
- 协方差矩阵同时供 `portfolio_risk` 模块复用

## 运行方式

```bash
python -m logic_layer.cross_asset_analysis.runner
```
