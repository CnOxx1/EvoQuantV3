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

## 计算公式

### 1. Pearson 相关性矩阵

输入：`{symbol: [close_prices...]}`，所有序列等长且时间对齐。

```
μ_A = (1/N) × Σ P_A(t)
σ_A = sqrt((1/(N-1)) × Σ (P_A(t) - μ_A)²)

Cov(A, B) = (1/(N-1)) × Σ (P_A(t) - μ_A) × (P_B(t) - μ_B)

Corr(A, B) = Cov(A, B) / (σ_A × σ_B)
```

- 输出 NxN 对称矩阵，对角线为 1.0
- 当某资产标准差为 0 时，相关性输出 0.0
- 结果 clip 到 [-1.0, 1.0]，保留 4 位小数

### 2. 相对强弱（Relative Strength）

基准：BTC/USDT（默认）

```
RS_period(symbol) = Return_period(symbol) / Return_period(BTC)
```

计算周期：1d、3d、7d

输出字段：

- `rs_vs_btc_7d` — 7 天相对强弱比
- `rs_vs_btc_3d` — 3 天相对强弱比
- `rs_vs_btc_1d` — 1 天相对强弱比
- `rs_rank` — 按 7d RS 降序排名
- `rs_momentum` — RS 动量方向：
  - `rising`：rs_7d > rs_3d（相对强弱在增强）
  - `falling`：rs_7d < rs_3d（相对强弱在减弱）
  - `stable`：rs_7d = rs_3d

### 3. 板块轮动（Sector Rotation）

```
Momentum = Return_7d / Volatility_7d
```

轮动阶段判定：

| 条件 | 阶段 | 含义 |
| --- | --- | --- |
| return > 0 且 momentum > 0.5 | `leading` | 领涨，动量强 |
| return > 0 且 momentum ≤ 0.5 | `weakening` | 上涨但动量衰减 |
| return ≤ 0 且 momentum > -0.5 | `improving` | 下跌但动量改善 |
| return ≤ 0 且 momentum ≤ -0.5 | `lagging` | 领跌，动量弱 |

输出字段：

- `sector_return_7d` — 板块 7 天收益率
- `sector_volatility_7d` — 板块 7 天波动率
- `sector_momentum_score` — 动量评分
- `sector_net_flow_24h` — 24 小时净流入
- `sector_oi_change_24h` — 24 小时持仓量变化
- `rotation_phase` — 轮动阶段

## 设计原则

- `calculator.py` 是纯函数，不依赖数据库，只接收对齐好的价格序列
- 所有序列必须等长且时间对齐后才传入计算
- 协方差矩阵同时供 `portfolio_risk` 模块复用

## 运行方式

```bash
python -m logic_layer.cross_asset_analysis.runner
```
