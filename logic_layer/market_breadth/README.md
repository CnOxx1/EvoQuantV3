# 市场广度模块 `market_breadth`

## 模块定位

`market_breadth` 不采集任何外部数据。

它只基于当前库里已经真实存在的：

- `exchange_data`
- `news_data`
- `tokenomics_data`

生成一份跨资产市场广度快照，回答下面这些问题：

- 当前 AI 真正能看到多少个“可直接使用”的市场资产
- 最近新闻流真正覆盖了多少个资产
- 未来 30 天真实解锁事件覆盖了多少个资产
- 当前市场视角更像“广市场 breadth”还是“极窄核心执行资产视角”

## 快速导航

- [模块速览](#模块速览)
- [设计原则](#设计原则)
- [当前输出](#当前输出)
- [当前运行方式](#当前运行方式)
- [当前存储](#当前存储)
- [维护约束](#维护约束)

## 模块速览

| 维度 | 当前情况 |
| --- | --- |
| 依赖 | `exchange_data / news_data / tokenomics_data` 的 AI-ready 主视图 |
| 核心问题 | 当前 AI 实际能看到多少资产、新闻覆盖和解锁覆盖 |
| 核心输出 | `breadth_status / breadth_score / assets / coverage_summary` |
| 查询范围 | 支持默认全市场视图与 `asset_keys` 子集过滤 |
| 存储 | `market_breadth_snapshots` |
| 质量原则 | 只按上游已经通过 AI-ready 过滤的真实视图统计广度，不直接回读 raw 原表偷算覆盖 |

## 设计原则

- 不接任何新外部 API
- 不制造任何伪造价格、伪造新闻、伪造解锁数据
- 只聚合数据库中已经落下来的真实样本
- 严格继承上游模块自己的 AI-ready 过滤口径

也就是说：

- `exchange_data` 里还没达到 `is_ready_for_ai=true` 的 source，不会被这里重新洗白
- `news_data` 里最近窗口没有进入 AI-ready 主视图的真实资产映射，就会直接表现成 `article_asset_count_72h=0`
- `tokenomics_data` 里没有进入 AI-ready 主视图的真实解锁事件，就会直接表现成 `unlock_asset_count_30d=0`
- 就算 raw 表里仍然躺着真实旧快照、旧新闻、旧解锁事件，只要这些内容已经被上游剥离，这里也不会继续把它们算进广度

当前实现还额外遵守一个很重要的口径：

- `exchange` 广度只按 `exchange_data.load_latest_market_context_bundle()` 中真正仍有可见 section 的资产计算
- `news` 广度只按 `news_data.load_latest_context_bundle()` 中的 `latest_articles` 计算
- `unlock` 广度只按 `tokenomics_data.load_latest_context_bundle()` 中的 `upcoming_unlock_events` 计算

也就是说，这里已经不再直接读 `news_articles` 或 `token_unlock_events` 原表来“偷算”广度。

## 当前输出

当前 `build_latest_context_bundle()` 会输出：

- `breadth_status`
  - `sufficient / narrow / thin`
- `breadth_score`
  - 基于真实资产覆盖、新闻资产覆盖、解锁资产覆盖计算的确定性广度分数
- `ai_ready_asset_count`
  - 当前来自真实 AI-ready 市场微观结构的资产数量
- `article_asset_count_72h`
  - 最近 72 小时真实新闻流覆盖到的资产数量
- `unlock_asset_count_30d`
  - 未来 30 天真实解锁事件覆盖到的资产数量
- `assets`
  - 每个资产当前的交易所、新闻、解锁三类真实证据摘要

现在 `coverage_summary` 也会显式区分：

- `exchange_symbol_count / exchange_visible_symbol_count`
- `news_article_count_72h / news_raw_article_count_72h`
- `unlock_event_count_30d / unlock_raw_event_count_30d`

这样可以直接看出“真实 raw 世界里还有多少东西”和“当前真正能给 AI 用的广度”之间的差距。

当前也支持按资产过滤：

- `asset_keys=["BTC","ETH"]`
- 或 CLI `--assets BTC,ETH`

这只影响本次查询范围，不会把过滤子集误包装成“默认全市场宇宙”。

## 当前运行方式

只输出当前广度上下文：

```bash
python -m logic_layer.market_breadth.runner --print-context
```

只看指定资产子集：

```bash
python -m logic_layer.market_breadth.runner --print-context --assets BTC,ETH,SOL
```

输出并保存快照：

```bash
python -m logic_layer.market_breadth.runner --save-snapshot
```

## 当前存储

快照会落到数据库表：

- `market_breadth_snapshots`

当前表只保存：

- 快照时间
- 广度状态
- 资产数量
- 广度分数
- 完整 bundle JSON

## 维护约束

- 如果修改广度评分规则，必须同步更新测试和本 README
- 如果重新引入任何直接读 raw 原表的统计，必须先证明不会绕过上游 AI-ready 过滤，否则不应接入
- 如果增加新的真实上游依赖，必须在这里明确写出来源
- 这个模块只做确定性市场广度聚合，不承载交易推断逻辑
