# 数据质量模块 `data_quality`

## 模块定位

`data_quality` 是 `data_layer` 内部的通用质量辅助模块。

它不负责采集任何外部数据，只负责回答两个问题：

- 当前某个数据源到底是 `ready / stale / error / empty / unconfigured` 中的哪一种状态
- 多个 source 的整体健康摘要应该怎么统一统计
- 当前整套数据层的关键证据带，到底有没有形成足够宽、足够诚实的市场世界模型

## 快速导航

- [模块速览](#模块速览)
- [当前职责](#当前职责)
- [为什么需要单独拆出来](#为什么需要单独拆出来)
- [当前文件](#当前文件)
- [当前输出语义](#当前输出语义)
- [跨模块真实证据带审计](#跨模块真实证据带审计)
- [维护约束](#维护约束)

## 模块速览

| 维度 | 当前情况 |
| --- | --- |
| 作用层级 | `data_layer` 共享质量与世界模型审计模块 |
| 核心问题 | 统一 source 健康状态、latest 质量口径与跨模块证据带 readiness |
| 关键输出 | `health_status`、`quality_flag` 汇总、`is_ready_for_ai`、`market_world_status` |
| 持久化 | `data_quality_audit_snapshots` 与 `collection_runs` |
| CLI 重点 | `--print-market-audit / --save-market-audit / --mode once / --mode scheduler` |
| 质量原则 | 只基于真实 coverage 与真实表计数做审计，不把“模块存在”误报成“证据带已就绪” |

## 当前职责

- 统一健康状态枚举
- 统一 source 健康状态判定
- 统一 coverage 汇总统计
- 统一 `quality_flag` 统计汇总
- 统一 latest 真实样本是否达到 AI-ready 质量门槛
- 统一跨模块真实证据带审计
- 统一跨模块真实证据带巡检调度与历史留痕

## 为什么需要单独拆出来

随着 `exchange_data / onchain_data / tokenomics_data / alternative_data` 持续扩源，单靠各模块自己判断：

- 数据是否为空
- 来源是否没配置
- 最新样本是否过期
- 当前 source 能不能继续给 AI 提供可靠输入

很容易出现口径漂移。

把这层判断单独收敛后，后续每个数据模块的 `load_source_coverage()` 都可以复用同一套语义。

## 当前文件

```text
data_quality/
  README.md
  __init__.py
  audit.py
  health.py
  runner.py
```

## 当前输出语义

当前统一支持下面这些健康状态：

- `ready`
- `stale`
- `error`
- `empty`
- `missing`
- `unconfigured`
- `disabled`
- `cooldown`

其中最关键的区分是：

- `empty`：来源跑了，但这次没有拿到数据
- `missing`：当前库里没有可用最新数据
- `unconfigured`：来源本身没接好，例如 endpoint 缺失
- `stale`：库里有数据，但已经过了可接受新鲜度窗口

当前还统一支持下面这些 `quality_flag` 汇总口径：

- `ok`
- `partial`
- `fallback`
- `stale`
- `unknown`

这些统计不是在判断 source 是否运行成功，而是在回答：

- 最新快照里有多少点是真正可直接信任的 `ok`
- 有多少点只是 `partial / fallback / stale`
- 当前 source 的 `latest_quality_ready_ratio` 到底是多少

当前共享层还提供 `is_quality_summary_ai_ready()`，统一回答：

- latest 快照里是否至少存在可直接使用的 `ok` 样本
- latest 快照里是否混入 `partial / fallback / stale / unknown`
- 当前 source 的 latest 样本质量是否已经干净到可以直接供 AI 使用

这层只判断样本质量，不判断：

- entity / factor / point 覆盖是否完整
- 推荐 venue 是否完整
- source 是否仍属于实验阶段

这些 completeness 约束仍保留在各业务模块里。

## 跨模块真实证据带审计

除了 source 级健康判断，当前共享层还新增了 `audit.py`，用于回答更高一层的问题：

- 当前 `exchange / macro / news / event_calendar / onchain / tokenomics / options / alternative`
  这些证据带里，哪些已经具备真实最新样本
- 哪些证据带虽然库里有历史，但还没有达到 `ready_for_ai`
- 哪些证据带其实仍是 `unconfigured / missing`
- 从“市场世界模型”角度看，当前数据层是 `ready / partial / blocked`

这层审计只使用两类真实事实：

- 各模块 `load_source_coverage()` 的当前健康与 AI-ready 结果
- 数据库里真实落下来的 `latest_* / history` 表计数

它不会：

- 构造任何占位数据
- 把“有因子目录但没有样本”伪装成已覆盖
- 把“模块存在”误报成“证据带已就绪”

手动查看当前真实审计状态：

```bash
python -m data_layer.data_quality.runner --print-market-audit
```

如果希望手动执行一次并把真实审计结果落库留档：

```bash
python -m data_layer.data_quality.runner --save-market-audit
```

如果希望按标准模块入口执行一次审计并落库：

```bash
python -m data_layer.data_quality.runner --mode once
```

如果希望常驻巡检，让系统持续判断“整套数据层是否真的足够给 AI 看市场”：

```bash
python -m data_layer.data_quality.runner --mode scheduler
```

调度频率由环境变量 `DATA_QUALITY_AUDIT_INTERVAL_SECONDS` 控制，默认 `300` 秒。
当前 `main.py` 也已经把这个模块注册为默认自动启动常驻模块 `data_quality_audit`。

输出里最关键的字段：

- `summary.world_model_status`
  - `ready`：所有 required 证据带都已经达到 `is_band_ready_for_ai=true`
  - `partial`：required 证据带都有真实历史/最新样本，但仍有带宽不足、stale 或 AI-ready 数量不足的问题
  - `blocked`：至少一条 required 证据带仍然是 `missing / unconfigured`
- `summary.critical_gap_band_names`
  - 当前仍然不满足 AI 直接使用门槛的 required 证据带
- `bands[].band_status`
  - `ready / stale / insufficient / unconfigured / missing`
- `bands[].latest_table_counts / history_table_counts`
  - 直接告诉你对应证据带是否真的有最新样本和历史样本
- `bands[].blocking_reasons`
  - 当前这条证据带为什么还不能算 AI-ready
- `asset_readiness_summary`
  - 资产级真实证据矩阵的摘要，不改变 `world_model_status`，但会直接告诉你
    当前有多少资产是 `ready / partial / thin / blocked`
  - 以及当前 `average_readiness_score` 和最值得交给 AI 分析的候选资产列表

也就是说，当前巡检现在同时回答两层问题：

- 数据层的 required 证据带整体是否已经成型
- 即使证据带整体还没 fully ready，当前有没有少数资产已经具备相对完整的真实证据链

这层的目标不是替代各模块自己的 coverage，而是把“局部 source 健康”汇总成“整套数据层是否足够支撑 AI 看市场”的统一事实摘要。

当前审计快照会持久化到数据库表 `data_quality_audit_snapshots`，方便后续观察：

- `world_model_status` 是不是长期停留在 `blocked`
- 哪些 `critical_gap_band_names` 总是反复出现
- required 证据带的 ready 数量是在增加还是减少

除了审计快照本身，当前 `--mode once / --mode scheduler / --save-market-audit`
还会把审计执行结果写入 `collection_runs`：

- `module_name=data_quality`
- `source_name=market_world_model`
- `job_name=market_world_audit`

这样后续不仅能看“当前世界模型是不是 blocked”，还可以直接看：

- 审计巡检任务最近有没有成功运行
- 最近一次审计花了多久
- 当时的 `world_model_status / critical_gap_count` 是什么

## 维护约束

- 如果新增健康状态，必须同步更新 `health.py` 和所有依赖 coverage 输出的 README / 测试。
- 如果新增 `quality_flag` 语义，必须同步更新 `health.py`、各模块 coverage README 和测试。
- 如果修改共享 AI-ready 质量门槛，必须同步更新 `tests/data_quality/test_health.py`。
- 如果修改跨模块证据带分层或 `world_model_status` 规则，必须同步更新 `audit.py`、本 README 和测试。
- 这里是数据层质量语义，不承载交易判断逻辑。
