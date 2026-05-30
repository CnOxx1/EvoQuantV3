# 宏观上下文模块 `macro_context`

## 模块定位

`macro_context` 属于逻辑处理层，负责读取 `macro_factor_catalog / macro_timeseries / latest_macro_timeseries`，把原始宏观时序整理成 AI 可直接消费的结构化上下文快照。

这个模块的目标不是输出“做多还是做空”的宏观结论，而是把 AI 在分析市场时真正需要的背景信息提前整理好，例如：

- 当前美元指数水平和最近 `1d / 5d` 变化
- 当前纳指和黄金的短中期变化
- 当前 `2Y / 10Y` 利率水平和最近变化
- 当前收益率曲线 `2s10s` 差值
- 每个因子的最新观测时间、新鲜度和是否 stale

## 快速导航

- [模块速览](#模块速览)
- [AI 文档维护约束](#ai-文档维护约束)
- [为什么需要这一层](#为什么需要这一层)
- [当前输入](#当前输入)
- [当前输出](#当前输出)
- [当前生成的特征](#当前生成的特征)
- [AI 直接消费的 bundle](#ai-直接消费的-bundle)
- [当前真实数据验证状态](#当前真实数据验证状态)
- [模块代码树](#模块代码树)
- [当前运行方式](#当前运行方式)
- [当前实现边界](#当前实现边界)
- [当前测试覆盖](#当前测试覆盖)

## 模块速览

| 维度 | 当前情况 |
| --- | --- |
| 核心任务 | 把原始宏观时序整理成可直接给 AI 使用的背景快照 |
| 主要输入 | `macro_factor_catalog / macro_timeseries / latest_macro_timeseries` |
| 核心输出 | `macro_context_snapshots` 与 `load_latest_context_bundle()` |
| 关键特征 | `1d / 5d` 变化、基点变化、收益率曲线、freshness 与 `is_ai_visible` |
| 视图分层 | `factors` 只保留 AI-visible，`raw_factors` 保留全部真实因子 |
| 质量原则 | stale 或语义不达标的真实因子不会继续混进 AI 主视图 |

## AI 文档维护约束

这份 README 是后续 AI 开发和维护 `macro_context` 时的工作文档，不只是功能介绍。

后续如果有 AI 修改了下面任一内容，必须同步更新当前 README：

- 模块代码树、文件职责或运行入口
- 输入输出表、变化计算规则、bundle 结构或上下游依赖
- 当前真实数据验证状态、测试覆盖或实现边界
- AI 直接消费字段、收益率曲线逻辑或 stale 语义
- `factors / raw_factors`、`coverage_summary`、`visibility_status` 或 `data_quality_flag` 语义

## 为什么需要这一层

`macro_data` 已经能稳定采集原始宏观因子，但 AI 如果每次都直接去读：

- `latest_macro_timeseries`
- `macro_timeseries`

再自己找参考点、计算 `1d / 5d` 变化、判断 stale、拼接收益率曲线，成本仍然偏高。

`macro_context` 做的就是把这些“解释市场必需但不该每次临时重算”的结构化背景特征沉淀下来。

现在它还额外强调一条质量原则：

- “数据库里有真实宏观点” 不等于 “这些点现在都应该直接暴露给 AI”
- stale 或语义未标准化的真实因子不会被伪装成当前可用上下文
- 被剥离的真实因子不会消失，而是留在 raw 诊断视图里

## 当前输入

- `macro_factor_catalog`
- `macro_timeseries`
- `latest_macro_timeseries`

## 当前输出

- `macro_context_snapshots`

这张表每一行对应一个 `factor_id + interval` 的最新上下文快照。

## 当前生成的特征

当前每个因子快照会包含：

- `latest_value`
- `observation_time`
- `freshness_seconds`
- `staleness_ttl_seconds`
- `is_stale`
- `change_1d_abs`
- `change_1d_pct`
- `change_5d_abs`
- `change_5d_pct`

对于 `macro_level` 因子，还额外生成：

- `change_1d_bps`
- `change_5d_bps`

这意味着 AI 不需要自己再把利率变化从百分比差转换成基点。

当前单因子上下文 payload 还会显式补充：

- `source_name / source_symbol / source_priority`
- `reference_1d_time / reference_5d_time`
- `reference_1d_available / reference_5d_available`
- `context_status`
  - `ready / partial / stale_only / raw_only`
- `context_quality_flags`
- `is_ai_visible`

这样 AI 不只知道“值和变化是多少”，也知道这条因子现在到底是完整可用、部分可用，还是只能保留在 raw 诊断里。

## AI 直接消费的 bundle

除了落库表，模块还提供一个 AI 友好的 bundle 输出：

- `MacroContextService.load_latest_context_bundle()`

当前 bundle 里包含：

- `as_of`
- `raw_as_of`
- `generated_at`
- `factor_count`
- `raw_factor_count`
- `excluded_factor_count`
- `ready_factor_count`
- `partial_factor_count`
- `stale_factor_count`
- `raw_only_factor_count`
- `missing_reference_1d_factor_count`
- `missing_reference_5d_factor_count`
- `coverage_score`
- `raw_coverage_score`
- `visibility_status`
- `coverage_summary`
- `data_quality_flag`
- `data_quality_flags`
- `quality_notes`
- `factors`
- `raw_factors`
- `cross_asset_context`
- `raw_cross_asset_context`

其中 `cross_asset_context` 当前首版先提供：

- `yield_curve_2s10s_bps`
- `yield_curve_2s10s_status`

也就是 `ust_10y_yield - ust_2y_yield` 的收益率曲线差值。

### `factors` 与 `raw_factors`

当前 bundle 已经明确区分：

- `factors`
  - 只保留 `AI-visible` 因子
  - 目前会剥离 `stale_only` 和 `raw_only` 因子
- `raw_factors`
  - 保留全部真实已生成因子
  - 用来解释哪些点存在，但当前不该直接给 AI 使用

这意味着：

- `factor_count` 现在表示 AI 主视图里的因子数量
- `raw_factor_count` 表示真实已生成的全部因子数量
- `coverage_score` 只按 AI-visible 因子计算
- `raw_coverage_score` 用来保留全部真实因子的 completeness 诊断

### `visibility_status`

当前 bundle 还会显式给出主视图可见性：

- `ready`
  - 全部真实因子都仍可直接进入 AI 主视图
- `partial`
  - 同时存在 AI-visible 因子和只保留在 raw 里的真实因子
- `raw_only`
  - 已有真实快照，但没有任何因子达到 AI-visible 门槛
- `missing`
  - 没有任何已生成快照

### `data_quality_flag`

当前 bundle 级质量标记使用：

- `ok`
  - 主视图完整且没有明显质量缺口
- `partial`
  - 主视图可用，但存在 stale 剥离、参考窗口缺失或部分因子降级
- `thin`
  - AI-visible 因子占比过低或 completeness 过薄
- `blocked`
  - 没有任何可直接给 AI 使用的宏观因子

更细的原因会继续落到：

- `data_quality_flags`
- `quality_notes`
- `coverage_summary`

## 当前真实数据验证状态

这个模块已经基于 `macro_data` 真实联网拉取并落库的宏观数据跑通过，而不是只对 mock 数据做结构设计。

当前已经验证可稳定生成的日频上下文包括：

- `dxy`
- `nasdaq_100`
- `gold_spot`
- `ust_2y_yield`
- `ust_10y_yield`
- `yield_curve_2s10s_bps`

但这些真实因子现在是否直接进入 `factors`，还要继续看：

- 当前点是否 stale
- `quality_flag` 是否已标准化
- `1d / 5d` 参考窗口是否完整

## 模块代码树

下面代码树省略 `__pycache__` 等缓存目录，只保留维护这个模块最常用的源码文件：

```text
logic_layer/
  macro_context/
    README.md                    # 模块说明、bundle 结构与维护约束
    __init__.py                  # 模块包入口
    models.py                    # 宏观上下文模型定义
    repository.py                # 宏观数据读取与快照落库
    service.py                   # 变化计算、stale 判断与 bundle 组装
    runner.py                    # CLI 运行入口
```

各文件职责：

- `models.py`
  - 配置模型和 `MacroContextSnapshot`
- `repository.py`
  - 读取 latest/history 宏观数据并写入 `macro_context_snapshots`
- `service.py`
  - 计算 `1d / 5d` 变化、stale 状态和 AI bundle
- `runner.py`
  - CLI 入口

## 当前运行方式

直接构建并落库：

```bash
python -m logic_layer.macro_context.runner
```

只看日频上下文：

```bash
python -m logic_layer.macro_context.runner --interval 1d
```

输出 AI bundle JSON 但不落库：

```bash
python -m logic_layer.macro_context.runner --interval 1d --no-save --print-bundle
```

## 当前实现边界

当前模块刻意保持克制：

- 只做上下文特征，不做方向性信号
- 不给出 risk-on / risk-off 打分
- 不做宏观事件解释
- 不做多源宏观因子融合

这样可以保证它更像“AI 的结构化背景层”，而不是过早把宏观结论写死。

## 当前测试覆盖

当前测试文件：

```text
tests/
  macro_context/
    test_macro_context_module.py
```

已覆盖：

- `market_price` 因子的 `1d / 5d` 变化计算
- `macro_level` 因子的基点变化计算
- `yield_curve_2s10s_bps` 聚合
- `AI-visible factors` 与 `raw_factors` 分离
- `stale_only` 因子从主视图剥离，但继续保留在 raw 诊断
- 缺少 `1d / 5d` 参考窗口时降级为 `partial`
- stale 查询子集降级为 `raw_only / blocked`
- 同一观测点重复重算时的 upsert 幂等性
