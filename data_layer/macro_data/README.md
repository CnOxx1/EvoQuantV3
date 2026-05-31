# 宏观跨市场数据采集模块 `macro_data`

## 模块定位

`macro_data` 是数据层里的跨市场宏观模块，负责获取美元指数、利率、纳指、黄金等非加密市场因子，做统一标准化后落库，供后续逻辑处理层和 AI 分析使用。

当前实现的核心目标非常明确：

- 给 AI 补齐加密市场之外的背景上下文
- 让 AI 在分析 BTC、ETH 或整体风险偏好时，不只看到币圈内部行情
- 用统一 `value` 语义和最新快照表，降低 AI 读取复杂度

## AI 文档维护约束

这份 README 是后续 AI 开发和维护 `macro_data` 时的工作文档，不只是功能介绍。

后续如果有 AI 修改了下面任一内容，必须同步更新当前 README：

- 模块代码树、文件职责或运行入口
- 因子目录、数据源、采集频率、环境变量或运行模式
- 历史表 / 快照表语义、质量规则、AI 读取方式或上下游依赖
- 联网验证结果、测试覆盖或实现边界

这个模块只负责：

- 拉取跨市场宏观原始数据
- 统一因子命名、时间语义、频率和单位
- 落库历史表与最新快照表

这个模块不负责：

- 输出交易信号
- 直接判断看多看空
- 宏观事件日历的事件解释

这些能力应该放到后续逻辑处理层。

## 快速导航

- [模块速览](#模块速览)
- [当前实现状态](#当前实现状态)
- [为什么这个模块对 AI 有价值](#为什么这个模块对-ai-有价值)
- [当前默认启用因子](#当前默认启用因子)
- [因子类型与统一字段语义](#因子类型与统一字段语义)
- [当前数据源](#当前数据源)
- [当前数据库表](#当前数据库表)
- [模块代码树](#模块代码树)
- [当前运行模式](#当前运行模式)
- [给 AI 的直接输入方式](#给-ai-的直接输入方式)
- [当前实现边界](#当前实现边界)

## 模块速览

| 维度 | 当前情况 |
| --- | --- |
| 目标 | 给 AI 补齐美元、利率、股指、黄金等跨市场背景 |
| 因子类型 | `market_price` 与 `macro_level` 两类 |
| 主要来源 | `yahoo_finance`、`fred` |
| 核心输出 | `macro_timeseries / latest_macro_timeseries / load_latest_context_bundle()` |
| 运行模式 | `bootstrap / once / scheduler` |
| 质量原则 | 只暴露真实已落库因子，AI 主视图与 `raw` 诊断明确分离 |

## 当前实现状态

当前代码已经完成：

- 宏观因子目录注册与入库
- `market_price` 和 `macro_level` 两类因子的分离采集
- 默认覆盖美元、风险资产、波动率、政策利率、前端利率、名义利率、真实利率、通胀预期和信用利差
- 历史时序表 `macro_timeseries`
- 最新快照表 `latest_macro_timeseries`
- `bootstrap / once / scheduler` 三种运行模式
- 针对 AI 当前市场分析的 `load_latest_context()` 读取入口
- `load_latest_context_bundle()` AI 可读宏观上下文聚合入口
- `load_source_coverage()` 宏观 source 覆盖率与新鲜度检查入口
- `load_latest_context_bundle()` 已直接输出 `configured_universe_summary / coverage_summary / source_health / source_health_summary / latest_quality_flag_breakdown / latest_quality_ready_ratio`
- `load_latest_context_bundle()` 现在只会把 `is_ready_for_ai=True` 的真实 source 暴露到 `row_count / source_counts / leaders / factors / latest_quality_*` 这些 AI 直接消费字段里；未达到 AI-ready 门槛但已真实落库的宏观快照不会伪造补齐，也不会继续混进主视图，而是保留在 `raw_as_of / raw_row_count / raw_source_counts / raw_latest_quality_* / ai_excluded_sources`
- latest 样本是否足够干净、能否直接给 AI 使用，现在与 `data_layer/data_quality` 的共享质量门槛保持一致，再叠加宏观模块自己的因子覆盖完整性约束
- `fred` 的最近一次采集链路现在也支持 best-effort 容错
  - 单个 FRED 序列超时不会再直接打断整次 `macro_level` 最新采集
  - 已成功拉到的真实利率因子会先落库
  - 失败因子保持缺失，由覆盖率 / AI-ready 质量门槛诚实暴露缺口
- 下游 `logic_layer.macro_context` 已开始消费这些表，进一步生成 AI 直接可读的宏观上下文快照
- 已完成一次真实联网拉取验证，成功写入 `dxy / nasdaq_100 / gold_spot / ust_2y_yield / ust_10y_yield`
- 当前实际采集主源为 `yahoo_finance` 和 `fred`
- `fred` CSV 日期列已适配真实返回中的 `observation_date`

当前没有实现：

- 宏观事件日历
- 多源并发对比
- 独立 `backfill` CLI 模式

## 为什么这个模块对 AI 有价值

纯加密市场数据只能告诉 AI“币圈内部发生了什么”，但很多关键波动实际上和更大的宏观背景相关。

当前模块已经能让 AI 同时看到：

- `dxy`
  - 美元强弱
- `ust_3m_yield`
  - 现金收益率和最前端利率锚
- `ust_2y_yield`
  - 短端利率预期
- `ust_10y_yield`
  - 长端利率与增长/通胀预期
- `ust_10y_real_yield`
  - 风险资产真实贴现压力
- `us_10y_breakeven_inflation`
  - 市场隐含通胀预期
- `us_bbb_oas / us_high_yield_oas`
  - 传统信用市场风险偏好和压力扩散
- `nasdaq_100`
  - 风险资产表现
- `gold_spot`
  - 避险资产表现

这样 AI 做市场分析时，就可以把：

- 交易所价格
- funding
- orderbook
- 新闻事件
- 宏观背景

放进同一时间上下文里解释，而不是孤立看币价。

## 当前默认启用因子

当前默认启用并参与采集的因子如下：

| `factor_id` | 因子类别 | 因子类型 | 频率 | 来源 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `dxy` | `dollar` | `market_price` | `1h` / `1d` | `yahoo_finance` | 美元指数 |
| `ust_2y_yield` | `rates` | `macro_level` | `1d` | `fred` | 美国 2 年期收益率 |
| `ust_10y_yield` | `rates` | `macro_level` | `1d` | `fred` | 美国 10 年期收益率 |
| `nasdaq_100` | `equity_index` | `market_price` | `1h` / `1d` | `yahoo_finance` | 纳斯达克 100 |
| `gold_spot` | `commodity` | `market_price` | `1h` / `1d` | `yahoo_finance` | 黄金价格代理，首版使用公开可稳定获取的黄金行情近似 |
| `fed_funds_upper` | `policy_rate` | `macro_level` | `1d` | `fred` | 联邦基金目标区间上沿 |
| `sp500` | `equity_index` | `market_price` | `1h` / `1d` | `yahoo_finance` | 更广义的风险偏好基准 |
| `vix` | `volatility` | `market_price` | `1h` / `1d` | `yahoo_finance` | 传统市场波动率与风险厌恶代理 |
| `ust_3m_yield` | `rates` | `macro_level` | `1d` | `fred` | 美国 3 个月期国债收益率 |
| `ust_30y_yield` | `rates` | `macro_level` | `1d` | `fred` | 美国 30 年期收益率 |
| `ust_10y_real_yield` | `real_rates` | `macro_level` | `1d` | `fred` | 美国 10 年期真实利率 |
| `us_10y_breakeven_inflation` | `inflation_expectation` | `macro_level` | `1d` | `fred` | 美国 10 年期盈亏平衡通胀率 |
| `us_bbb_oas` | `credit_spread` | `macro_level` | `1d` | `fred` | 美国 BBB 公司债 OAS |
| `us_high_yield_oas` | `credit_spread` | `macro_level` | `1d` | `fred` | 美国高收益债 OAS |
| `wti_crude` | `commodity` | `market_price` | `1h` / `1d` | `yahoo_finance` | 原油价格代理 |

这些因子已经足够覆盖：

- 美元方向
- 前端利率
- 长端名义利率
- 长端真实利率
- 通胀预期
- 信用压力
- 风险资产
- 避险资产
- 宏观波动与能源冲击

对 AI 的日常市场分析已经不只是首版锚点，而是一个可以直接判断宏观 risk-on / risk-off、流动性收紧和信用扩散的可用输入层。

## 当前可按需关闭的扩展因子

这些因子已经写进 `macro_factor_catalog`，当前默认启用，但仍建议通过环境变量按需关闭：

- `fed_funds_upper`
- `sp500`
- `vix`
- `ust_3m_yield`
- `ust_30y_yield`
- `ust_10y_real_yield`
- `us_10y_breakeven_inflation`
- `us_bbb_oas`
- `us_high_yield_oas`
- `wti_crude`

这样做的目的不是制造可选数据，而是允许你在真实上游发生频率变化、历史窗口受限或运维资源不足时，显式收缩宏观输入宇宙。

## 因子类型与统一字段语义

当前实现显式区分两类因子：

### 1. `market_price`

适用：

- `dxy`
- `nasdaq_100`
- `gold_spot`
- `sp500`
- `vix`
- `wti_crude`

特点：

- 更像传统市场行情
- 保留 `open/high/low/close/volume`
- 当前支持 `1h`、`1d`

### 2. `macro_level`

适用：

- `fed_funds_upper`
- `ust_3m_yield`
- `ust_2y_yield`
- `ust_10y_yield`
- `ust_30y_yield`
- `ust_10y_real_yield`
- `us_10y_breakeven_inflation`
- `us_bbb_oas`
- `us_high_yield_oas`

特点：

- 更像低频宏观观测值
- 当前只做 `1d`
- 最重要的是 `observation_time` 和数据新鲜度，而不是高频更新

### 统一 `value` 规则

为了让 AI 和逻辑层读取简单，当前实现强制了一条统一规则：

- 所有因子都必须有 `value`
- 对 `market_price` 因子，`value = close`
- 对 `macro_level` 因子，`value = 原始观测值`

这样上层不需要先判断因子类型，再决定该取 `close` 还是别的字段。

## 当前数据源

当前实现只接单主源，不做多源并发聚合。

### `market_price` 来源

- `yahoo_finance`
  - 通过图表接口获取 `1h / 1d` 序列
  - 当前用于：
    - `dxy`
    - `nasdaq_100`
    - `gold_spot`
    - `sp500`
    - `vix`
    - `wti_crude`

### `macro_level` 来源

- `fred`
  - 通过公开 CSV 接口获取日频序列
  - 当前已适配真实返回中的 `observation_date` 日期列
  - 当前用于：
    - `fed_funds_upper`
    - `ust_3m_yield`
    - `ust_2y_yield`
    - `ust_10y_yield`
    - `ust_30y_yield`
    - `ust_10y_real_yield`
    - `us_10y_breakeven_inflation`
    - `us_bbb_oas`
    - `us_high_yield_oas`

当前新增的 FRED 序列 ID 已按 FRED 官方目录配置：

- `DGS3MO`
- `DFII10`
- `T10YIE`
- `BAMLC0A4CBBB`
- `BAMLH0A0HYM2`

需要注意：

- `us_bbb_oas / us_high_yield_oas` 的历史深度受 FRED 上游可提供窗口限制，不能简单假设一定能回填满配置里的全部年数
- 这不会制造任何伪数据，只代表 credit spread 因子的真实历史跨度可能短于国债利率序列

当前代码结构已经预留了：

- `source_priority`
- disabled P1 因子
- 不同 `source_kind` adapter

这意味着后面扩源时不需要重写整套表结构。

## 当前真实联网验证结果

当前模块已经基于真实外部数据源完成了一次落库验证，而不只是本地 mock：

- `yahoo_finance`
  - 成功拉取并写入 `dxy`、`nasdaq_100`、`gold_spot`
- `fred`
  - 成功拉取并写入 `ust_2y_yield`、`ust_10y_yield`
  - 已兼容真实 CSV 返回中的 `observation_date` 字段

这意味着 `macro_data` 当前不是停留在目录设计阶段，而是已经能持续为下游 `logic_layer.macro_context` 和 AI 上下文读取链路提供真实宏观输入。

需要区分两件事：

- 已经在本项目里完成真实联网落库验证的，是 `dxy / nasdaq_100 / gold_spot / ust_2y_yield / ust_10y_yield`
- 这次新增的 FRED 因子采用的也都是真实官方序列，不是伪造字段，但它们的运行时可用性仍应以你本地实际采集结果为准

## 标准化与质量语义

当前采集链路固定为：

1. source fetch
2. normalize
3. validate
4. upsert history
5. refresh latest

标准化后最重要的字段是：

- `factor_id`
- `factor_type`
- `interval`
- `observation_time`
- `value`
- `quality_flag`
- `source_name`
- `source_symbol`
- `source_priority`

### 时间语义

当前实现已经显式区分：

- `observation_time`
  - 该数据点代表的真实市场时间
- `collected_at`
  - 本地采集入库时间

这点对 AI 很重要。否则后面做联动分析时，容易把“发布时间”和“市场时间”混成一个字段。

### 质量语义

当前实现支持的 `quality_flag`：

- `ok`
- `stale`
- `partial`
- `fallback`

当前首版实际会用到的主要是：

- `ok`
- `stale`

最新一条样本如果超过因子目录中的 `staleness_ttl_seconds`，会被标记成 `stale`，方便 AI 判断当前宏观上下文是否过期。

## 当前数据库表

### 1. `macro_factor_catalog`

作用：

- 保存因子目录、来源、频率和新鲜度规则

当前关键字段：

- `factor_id`
- `category`
- `factor_type`
- `default_interval`
- `source_name`
- `source_symbol`
- `staleness_ttl_seconds`
- `is_intraday_enabled`
- `enabled`

### 2. `macro_timeseries`

作用：

- 保存宏观历史时序
- 是后续 AI 和逻辑层做回看、拼接、联动分析的主输入

当前关键字段：

- `factor_id`
- `interval`
- `observation_time`
- `value`
- `open/high/low/close`
- `quality_flag`
- `raw_payload_json`

唯一键：

- `UNIQUE(factor_id, interval, observation_time)`

### 3. `latest_macro_timeseries`

作用：

- 保存每个 `factor_id + interval` 的当前最新样本
- 优先服务 AI 当前市场分析，而不是回测

当前关键字段：

- `factor_id`
- `interval`
- `observation_time`
- `value`
- `quality_flag`
- `source_name`
- `source_symbol`

唯一键：

- `UNIQUE(factor_id, interval)`

## 模块代码树

下面代码树省略 `__pycache__` 等缓存目录，只保留维护这个模块最常用的源码文件：

```text
data_layer/
  macro_data/
    README.md                    # 模块说明、因子范围与维护约束
    __init__.py                  # 模块包入口
    models.py                    # 因子目录与标准化时序模型
    sources.py                   # P0 / P1 因子定义与来源配置
    client.py                    # Yahoo Finance / FRED 请求封装
    market.py                    # 市场型宏观因子采集
    rates.py                     # 利率型宏观因子采集
    service.py                   # 模块编排、目录同步与调度
    runner.py                    # CLI 运行入口
```

各文件职责：

- `models.py`
  - 因子目录模型、标准化时序模型、统一 `value` 规则
- `sources.py`
  - P0 / P1 因子目录定义
- `client.py`
  - `yahoo_finance` / `fred` 请求封装与重试
- `market.py`
  - `market_price` 因子采集与落库
- `rates.py`
  - `macro_level` 因子采集与落库
- `service.py`
  - 模块统一编排入口、目录同步、scheduler、AI 上下文读取
- `runner.py`
  - CLI 入口

## 当前运行模式

`runner.py` 当前支持 3 种模式：

- `bootstrap`
  - 初始化因子目录并回填历史
- `once`
  - 执行一次最新数据采集
- `scheduler`
  - 按频率长期更新

### `bootstrap` 做什么

- 同步 `macro_factor_catalog`
- 回填 `market_price` 的 `1h / 1d` 历史
- 回填 `macro_level` 的 `1d` 历史
- 更新 `latest_macro_timeseries`

当前启动回填还有两个质量与稳定性约束：

- `macro_level` 在回填历史时会按时间窗口拆分 FRED 请求，避免长区间单请求过大导致整个模块启动失败
- 默认 `bootstrap` 和 `scheduler` 启动回填都会使用 best-effort 容错
  - 如果单个宏观因子请求超时，模块会记录错误日志并继续启动后续调度，而不是直接退出整个常驻进程
  - 这不会制造任何伪数据，只会保留已经成功获取到的真实历史样本
- `scheduler` 模式下如果启动回填阶段仍抛出未被单因子容错吸收的异常，当前 runner 也会把这次异常降级成日志并继续进入常驻调度
  - 这意味着系统会优先保住后续真实增量供数，再由 `data_quality_audit` 把当前宏观证据带是否 `stale / partial / blocked` 诚实暴露出来
- 如果你确实希望 bootstrap 阶段 fail-fast，可以显式传 `--strict-bootstrap`
  - 这样遇到单个上游失败会立刻退出，适合手工排查上游问题时使用

### `once` 做什么

- 拉最近一段窗口内的最新市场数据
- upsert 到历史表
- 刷新最新快照表
- `fred` 最新采集默认 best-effort
  - 如果单个利率因子超时，本次 `once` 仍会保留已经成功获取到的真实利率样本
  - 未成功的因子不会补假数据，只会继续在 coverage / bundle 里表现为缺失或未达到 AI-ready

### `scheduler` 做什么

- `market_price`
  - 默认每 `15m`
- `macro_level`
  - 默认每日 `1` 次

当前 `scheduler` 模式同时支持两种调度器：

- `BlockingScheduler`（默认）：传统阻塞式调度
- `AsyncIOScheduler`（通过 `--async-scheduler` 开启）：利用 asyncio 事件循环调度，适合与其他 async 组件共存的部署环境

```bash
# 默认 BlockingScheduler
python -m data_layer.macro_data.runner --mode scheduler

# AsyncIOScheduler
python -m data_layer.macro_data.runner --mode scheduler --async-scheduler
```

如果你更关心先把常驻采集跑起来，而不是强依赖启动时的全量历史回填，可以：

- 保持默认行为，让模块在启动时尽量补齐历史，但单因子超时不会打死整个 `macro_data`
- 或显式使用 `--skip-bootstrap`，直接进入常驻调度
- 或显式使用 `--strict-bootstrap`，把 best-effort 改回严格失败模式
- 常驻阶段的 `fred` 最新轮询同样遵循这个原则
  - 单个 FRED 因子超时会被记录为局部失败日志
  - 同轮中已经成功获取的其他真实因子仍会正常写入
  - 后续是否可直接喂给 AI，不由“这轮 job 有没有抛异常”决定，而由最新真实覆盖率和新鲜度共同决定

另外，当前总入口 `main.py` 对 `macro_data` 这类常驻数据模块也已经改成“失败模块自动重启/隔离失败实例”的策略：

- 单个 `macro_data` 进程意外退出时，优先自动重启该模块
- 如果短窗口内连续退出次数过多，则只隔离这个失败模块，不再把 `exchange_data / news_data / onchain_data` 等其他真实供数链一起停掉
- 这样 `data_quality_audit` 才能继续基于剩余真实数据诚实报告缺口，而不是把整套数据层一起打成离线

这符合当前目标：给 AI 稳定提供宏观上下文，而不是把宏观数据采成交易所 ticker 一样的超高频。

## 当前环境变量

当前实现支持这些配置项：

- `MACRO_ENABLE_FED_FUNDS_UPPER`
- `MACRO_ENABLE_SP500`
- `MACRO_ENABLE_VIX`
- `MACRO_ENABLE_UST_3M_YIELD`
- `MACRO_ENABLE_UST_30Y_YIELD`
- `MACRO_ENABLE_UST_10Y_REAL_YIELD`
- `MACRO_ENABLE_US_10Y_BREAKEVEN_INFLATION`
- `MACRO_ENABLE_US_BBB_OAS`
- `MACRO_ENABLE_US_HIGH_YIELD_OAS`
- `MACRO_ENABLE_WTI_CRUDE`
- `MACRO_MARKET_INTERVAL_SECONDS`
  - `market_price` 调度频率，默认 `900`
- `MACRO_LEVEL_INTERVAL_SECONDS`
  - `macro_level` 调度频率，默认 `86400`
- `MACRO_TIMEOUT_SECONDS`
  - 单次请求超时，默认 `20`
- `MACRO_MARKET_HISTORY_DAYS`
  - `bootstrap` 时小时级历史回填天数，默认 `90`
- `MACRO_DAILY_HISTORY_YEARS`
  - `bootstrap` 时日频历史回填年数，默认 `5`
- `MACRO_RECENT_MARKET_LOOKBACK_DAYS`
  - `once / scheduler` 时市场因子回看窗口，默认 `10`
- `MACRO_RECENT_RATE_LOOKBACK_DAYS`
  - `once / scheduler` 时利率因子回看窗口，默认 `30`
- `MACRO_USER_AGENT`
  - HTTP 请求头

## 给 AI 的直接输入方式

当前模块最直接服务 AI 的不是历史表，而是：

- `latest_macro_timeseries`
- `MacroDataService.load_latest_context()`
- `MacroDataService.load_latest_context_bundle()`
- `MacroDataService.load_source_coverage()`

这能稳定支持下面这类调用：

- 取最新 `dxy / sp500 / nasdaq_100 / gold_spot / vix / wti_crude`
- 取最新 `fed_funds_upper / ust_3m_yield / ust_2y_yield / ust_10y_yield / ust_30y_yield`
- 取最新 `ust_10y_real_yield / us_10y_breakeven_inflation / us_bbb_oas / us_high_yield_oas`
- 判断某个因子的 `quality_flag` 是否为 `stale`
- 按 `interval` 过滤当前可用的宏观上下文
- 按 `factor_ids` 精确过滤 coverage 统计，而不是把无关因子也算进 source 完整度
- 直接读取 bundle 里的 `coverage_summary / source_health_summary / latest_quality_flag_breakdown`
- 判断宏观 source 是否 ready，以及当前证据是否缺失了 `front_end_rates / rates_curve / real_rates / inflation_expectation / credit_stress`

这里需要特别区分：

- `health_status=ready`
  - 表示 source 最近运行成功，且没有 stale / error 这类运行层问题
- `is_ready_for_ai=True`
  - 比 `ready` 更严格
  - 不只要求任务最近成功，还要求当前过滤条件下因子覆盖完整，且 latest 快照里至少存在可直接使用的 `ok` 样本
  - 如果一个宏观 source 当前只有 `partial / fallback` 样本，或者设计内因子还没抓全，即使任务刚跑完，也不应直接当成 AI 可依赖的宏观锚点
- `data_quality_flags`
  - source 级结构化质量标签
  - 当前会显式区分例如 `factor_coverage_incomplete / partial_points_present / fallback_points_present / stale_points_present / unknown_quality_flag_present`

bundle 里现在建议优先读取：

- `configured_universe_summary`
  - 用来判断“当前默认启用的宏观宇宙本身够不够宽”
  - 这层不是补值，而是显式告诉 AI：现在看到的是完整的宏观世界观，还是被裁剪过的默认配置
- `coverage_summary`
  - 包括 `coverage_by_source`
- `source_health_summary`
  - 包括 `ready_for_ai_source_count / not_ready_for_ai_source_count`
- `source_health`
  - 直接看每个 source 的 `is_ready_for_ai`
  - 以及每个 source 的 `data_quality_flags`

这比让 AI 直接处理外部 ticker 和原始 payload 更稳定。

## 当前测试覆盖

当前测试文件：

```text
tests/
  macro_data/
    test_macro_module.py
```

当前已覆盖：

- `market_price` 的 `value = close`
- `macro_level` 的 newer-only 最新快照更新规则
- 因子目录的 P0 / 扩展因子启停写入
- scheduler 的线程安全包装路径
- `collection_runs` 写入、`load_source_coverage()` 和 `load_latest_context_bundle()` 聚合
- `load_source_coverage()` 在 `factor_ids` 过滤下的精确统计
- coverage 里的 `quality_flag` 汇总字段
- bundle 里的 `coverage_summary / source_health / source_health_summary / latest_quality_flag_breakdown`
- bundle 已新增 `configured_universe_summary`
- 宏观证据缺口标记，例如 `real_rates / inflation_expectation / credit_stress`

### 2026-05-15 本地验证记录

本轮围绕宏观 source 的 AI 可用性语义完成了下面这些本地验证：

- `python -m py_compile data_layer/macro_data/service.py tests/macro_data/test_macro_module.py`
  - 通过
- `pytest -q tests/macro_data/test_macro_module.py`
  - `15 passed`

这轮验证说明：

- `coverage_summary` 已新增 `coverage_by_source`
- `configured_universe_summary` 现在会直接暴露默认启用因子的 factor/category/source/region 宽度，以及缺失了哪些关键宏观语义组
- `source_health_summary` 已新增 `ready_for_ai_source_count / not_ready_for_ai_source_count`
- `macro_data` 的 `is_ready_for_ai` 不再等价于 `health_status=ready`
- 如果某个宏观 source 只有 `fallback` 样本，即使最近任务成功，也会被明确降级为 `is_ready_for_ai=False`
- 如果某个宏观 source 只覆盖了部分设计内因子，即使最近任务成功，也会被明确降级为 `is_ready_for_ai=False`
- source coverage 现在也会直接输出结构化 `data_quality_flags`，不再只把“为什么不能给 AI 用”藏在文字说明里
- 如果默认启用的宏观宇宙本身过窄，即使已启用 source 都完整成功，bundle 也会额外标记 `macro_configured_market_breadth_limited`

## 当前实现边界

这一版是为 AI 提供“稳定、可解释、可读取”的宏观背景，不是为了把所有宏观数据一次性做全。

当前明确的边界是：

- 只做连续时序，不做宏观事件日历
- 只接单主源
- 先保证统一语义和最新快照可用

如果继续往下扩，最合理的下一步是：

1. 增加独立 `backfill` 模式
2. 再考虑 `macro_releases` 这类事件表
3. 给 `vix / rates / dxy` 增加多源交叉验证
4. 把 credit spread 历史窗口限制显式暴露到 bundle 元数据里
