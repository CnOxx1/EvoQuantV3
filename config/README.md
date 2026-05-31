# 配置模块 `config`

## 模块定位

`config` 是项目的全局配置中心，集中管理数据库路径、交易所连接、资产宇宙定义、采集层级和日志设置。

所有其他模块通过 `from config.settings import ...` 或 `from config.symbols import ...` 获取运行参数，不在各自模块内硬编码路径或符号列表。

## 模块代码树

```text
config/
  __init__.py              # 包入口
  settings.py              # 全局设置：数据库路径、交易所配置、日志级别
  symbols.py               # 资产宇宙定义：符号、层级、板块分组
  collection_tiers.py      # 采集频率层级配置
  logging.py               # 日志格式与输出配置
```

## 核心配置项

### 数据库路径

| 变量 | 用途 |
| --- | --- |
| `DATABASE_PATH` | 主数据库（crypto_data.db） |
| `EXCHANGE_DATA_DB_PATH` | 交易所域数据库（exchange_data.db） |
| `MARKET_DATA_DB_PATH` | 市场数据库（market_data.db） |
| `ANALYTICS_DB_PATH` | 分析结果数据库（analytics.db） |

数据库域拆分通过 `DB_SPLIT_ENABLED` 环境变量控制，默认启用。

### 资产宇宙

`symbols.py` 定义了 `SYMBOL_UNIVERSE`，每个资产包含：

- `symbol` — 交易对（如 `BTC/USDT`）
- `tier` — 采集层级（`core / active / monitor`）
- `sector` — 板块分类（如 `store_of_value / smart_contract_l1 / defi`）

层级决定采集频率：

- `CORE`：最高频（orderbook 3s, derivatives 60s）
- `ACTIVE`：中频（orderbook 10s, derivatives 300s）
- `MONITOR`：低频（orderbook 30s, derivatives 900s）
