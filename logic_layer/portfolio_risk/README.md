# 组合风险计算模块 `portfolio_risk`

## 模块定位

`portfolio_risk` 属于逻辑处理层，负责计算组合级别的波动率、VaR、集中度和分散化指标。

它是纯计算模块，不采集外部数据，基于 `cross_asset_analysis` 提供的协方差矩阵和假设权重进行风险分解。

## 模块代码树

```text
logic_layer/portfolio_risk/
  __init__.py       # 包入口
  models.py         # 数据模型定义
  calculator.py     # 纯计算引擎（不依赖数据库）
  repository.py     # 数据读取与结果落库
  service.py        # 编排入口
  runner.py         # CLI 运行入口
```

## 计算公式

### 1. 组合波动率（Portfolio Volatility）

```
σ²_portfolio = w^T × Cov × w = ΣΣ w_i × w_j × Cov(i,j)
σ_portfolio = sqrt(σ²_portfolio)
```

- `w` = 权重向量，`Σw_i = 1.0`
- `Cov` = 协方差矩阵（由 `cross_asset_analysis` 提供）

年化波动率：

```
σ_annual = σ_daily × sqrt(365)
```

使用 365 天而非 252 天，因为加密市场全年无休。

### 2. 在险价值（Value at Risk）

参数法，假设正态分布：

```
VaR_95% = σ_daily × 1.645
VaR_99% = σ_daily × 2.326
```

含义：在 95%/99% 置信度下，单日最大预期损失比例。

### 3. 风险贡献（Risk Contribution）

```
MC_i = (Cov × w)_i = Σ_j (Cov(i,j) × w_j)
RC_i = w_i × MC_i / σ_portfolio
```

- `MC_i` = 资产 i 的边际风险贡献
- `RC_i` = 资产 i 的风险贡献（绝对值）
- `Σ RC_i = σ_portfolio`

### 4. 协方差矩阵构建

从相关性矩阵和个体波动率构建：

```
Cov(i, j) = Corr(i, j) × σ_i × σ_j
```

- `Corr(i, j)` 来自 `cross_asset_analysis` 的 Pearson 相关性矩阵
- `σ_i` 为资产 i 的日度波动率

### 5. 集中度（Concentration）

HHI（Herfindahl-Hirschman Index）：

```
HHI = Σ w_i²
```

- HHI = 1.0 表示完全集中在单一资产
- HHI = 1/N 表示等权分配

有效资产数：

```
Effective_N = 1 / HHI
```

### 6. 分散化比率（Diversification Ratio）

```
DR = (Σ w_i × σ_i) / σ_portfolio
```

- DR > 1 表示分散化产生了风险降低效果
- DR = 1 表示资产完全正相关，无分散化收益
- DR 越大，分散化效果越好

## 设计原则

- `calculator.py` 是纯函数，只接收权重和协方差矩阵
- 不做任何交易建议或仓位推荐
- 只输出风险度量，供 AI 和策略层自行决策

## 运行方式

```bash
python -m logic_layer.portfolio_risk.runner
```
