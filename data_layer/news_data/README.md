# 新闻数据采集模块 `news_data`

## 模块定位

`news_data` 是数据层里的新闻采集模块，负责从互联网抓取加密货币相关新闻，做统一标准化后落库，供后续逻辑处理层和 AI 调用分析。

从 AI 输入结构看，`news_data` 提供的是“原始文本与事件层”。完整市场分析不应该只读新闻，还应该把它和 `logic_layer.technical_indicators` 的行情特征、`logic_layer.exchange_comparison` 的跨交易所横截面特征、`logic_layer.macro_context` 的跨市场宏观背景一起使用。

## AI 文档维护约束

这份 README 是后续 AI 开发和维护 `news_data` 时的工作文档，不只是功能介绍。

后续如果有 AI 修改了下面任一内容，必须同步更新当前 README：

- 模块代码树、文件职责或运行入口
- 新闻源清单、抓取方式、去重策略、环境变量或调度方式
- 字段定义、文本标准化语义、上下游依赖关系
- 当前边界、测试覆盖或推荐扩展方向

当前版本先聚焦：

- 新闻源：公开 RSS / Atom feed
- 数据类型：标题、摘要、正文纯文本、发布时间、作者、标签、命中币种、原始 payload
- 输出表：`news_articles`

当前实现同时提供：

- 同步采集入口，适合 CLI / scheduler
- 异步采集入口，适合后续接入 FastAPI、异步任务和 AI 服务
- 采集覆盖快照入口，可直接查看每个新闻源最近一次采集状态、数量、新鲜度和 AI 可用性判断
- AI 上下文 bundle 入口，可直接输出最近新闻窗口的来源分布、资产提及、质量缺口、默认跟踪资产宇宙 breadth 诊断和最新文章列表
  - 其中 AI 直接消费的 `article_count / source_counts / latest_articles` 现在只保留 `is_ready_for_ai=true` 的真实新闻源
  - 未达到 AI-ready 门槛但已经真实落库的新闻不会消失，会保留在 `raw_article_count / raw_source_counts / raw_text_completeness_summary / ai_excluded_sources / source_health`

这个模块只负责：

- 拉取新闻
- 标准化字段
- 去重
- 落库

这个模块不负责：

- 情绪分析
- 事件打标
- 因子构建
- 新闻与价格联动策略判断

这些能力应该放到后续逻辑处理层。

## 快速导航

- [模块速览](#模块速览)
- [为什么先用 RSS / Atom](#为什么先用-rss--atom)
- [标准化后的字段](#标准化后的字段)
- [模块代码树](#模块代码树)
- [去重与更新策略](#去重与更新策略)
- [采集覆盖检查](#采集覆盖检查)
- [当前配置项](#当前配置项)
- [当前默认源明细](#当前默认源明细)
- [当前资产命中注册表](#当前资产命中注册表)
- [运行方式](#运行方式)
- [后续建议](#后续建议)

## 模块速览

| 维度 | 当前情况 |
| --- | --- |
| 主输入角色 | 提供原始文本、发布时间、作者、标签与资产命中结果 |
| 默认抓取方式 | 公开 `RSS / Atom` feed |
| 核心输出表 | `news_articles` |
| 主 bundle | `load_latest_context_bundle()` |
| 来源组织 | `core_media / market_intelligence / ecosystem / governance_forum / research_security_regulatory` |
| 质量原则 | AI 主视图只保留 `is_ready_for_ai=true` 的真实新闻源，其他样本保留在 `raw_*` 诊断里 |

## 为什么先用 RSS / Atom

对数据层来说，RSS / Atom 是一个更稳妥的起点：

- 不依赖 API key
- 结构化程度高，适合统一解析
- 容易做定时调度
- 便于后续继续扩到公告页、博客 API、社媒聚合

当前默认新闻源：

- 综合媒体：
  - `CoinDesk`
  - `Cointelegraph`
  - `Decrypt`
  - `CryptoSlate`
  - `BeInCrypto`
  - `NewsBTC`
  - `AMBCrypto`
  - `CryptoPotato`
  - `CoinJournal`
- 市场研究 / 深度内容：
  - `Blockworks`
  - `Bitcoin Magazine`
  - `The Defiant`
  - `99Bitcoins`
- 官方生态 / 协议博客：
  - `Arbitrum`
  - `Chainlink Blog`
  - `Sui Blog`
  - `Sonic Blog`
  - `Sei Blog`
  - `Lido Blog`
  - `1inch Blog`
  - `Synthetix Blog`
  - `EigenLayer Blog`
  - `SatLayer Blog`
  - `Avail Blog`
  - `Celestia Blog`
  - `RedStone Blog`
  - `QuickNode Blog`
- 治理 / 社区论坛：
  - `Lido Research`
  - `EigenLayer Forum`
  - `Arbitrum Forum`
  - `ENS Governance`
  - `Sky Forum`
  - `dYdX Forum`
  - `Safe Forum`
  - `Starknet Community`
  - `CoW DAO Forum`
  - `Gitcoin Governance`
  - `Osmosis Community Hall`
  - `Celestia Forum`
  - `Zcash Community Forum`
  - `Babylon Forum`
  - `Polkadot Forum`
  - `Cosmos Hub Forum`
  - `Nym Forum`
  - `Berachain Forum`
  - `Scroll Forum`
  - `Initia Forum`
  - `Aztec Forum`
  - `Connext Forum`
  - `Pyth DAO Forum`
- 研究 / 安全 / 合规 / 监管：
  - `Chainalysis`
  - `Immunefi`
  - `SEC Press Releases`
  - `Elliptic`
  - `CFTC General Press Releases`
  - `CFTC Enforcement Actions`
  - `Trail of Bits`

如果后面要新增源，可以通过环境变量 `NEWS_EXTRA_FEEDS_JSON` 追加，不需要改数据库结构。

这些默认源的设计目标不是“越多越好”，而是先覆盖五类高价值输入：

- 高频新闻流：适合做事件触发、标题情绪、热点监控
- 市场解读流：适合补充行情背景、叙事方向和研究观点
- 官方生态流：适合补充协议升级、生态活动、产品发布和技术路线
- 治理讨论流：适合补充提案、参数调整、论坛争议和社区信号
- 研究 / 安全 / 监管流：适合补充监管、链上安全、调查类事件

每个新闻源还会带一个 `source_group`，用于更快按采集职责组织来源：

- `core_media`
- `market_intelligence`
- `ecosystem`
- `governance_forum`
- `research_security_regulatory`

## 标准化后的字段

`news_articles` 当前主要保存这些字段：

- `source`
- `source_type`
- `feed_url`
- `category`
- `title`
- `summary`
- `content_text`
- `url`
- `url_hash`
- `author`
- `published_at`
- `collected_at`
- `language`
- `relevance_symbols`
- `tags`
- `image_url`
- `external_id`
- `raw_payload_json`

说明：

- `url_hash` 用于跨轮次去重
- `source_type` 会准确标记为 `rss` 或 `atom`
- `relevance_symbols` 当前会根据标题和正文命中 `BTC / ETH / SOL / SUI / USDT / USDC / DAI / FDUSD`
  - 当前别名注册表已经扩展到更大的主流交易资产与生态代币集合，包括 `BTC / ETH / SOL / SUI / BNB / XRP / DOGE / ADA / TRX / TON / AVAX / LINK / ARB / OP / AAVE / UNI / LDO / SEI / TIA / PYTH / STRK / DYDX / ENS / DOT / ATOM / OSMO / ZEC / 1INCH / SNX / EIGEN / GTC / COW / SAFE / ONDO / ENA / WLD / USDT / USDC / DAI / FDUSD`
  - 这层仍然只做基于真实文本的显式命中，不会推断隐含情绪，也不会伪造未提及对象
- `content_text` 优先使用 feed 中的正文内容，没有则退化为摘要文本
- `raw_payload_json` 保留解析后的原始字段，方便后续补逻辑

## 模块代码树

下面代码树省略 `__pycache__` 等缓存目录，只保留维护这个模块最常用的源码文件：

```text
data_layer/
  README.md                      # 数据层总览文档
  news_data/
    README.md                    # 模块说明、新闻源与维护约束
    __init__.py                  # 模块包入口
    models.py                    # 新闻源与标准化文章模型
    sources.py                   # 默认 RSS / Atom 源配置
    client.py                    # feed 下载与解析
    collector.py                 # 筛选、去重与落库
    service.py                   # 模块编排与调度
    runner.py                    # CLI 运行入口
    registry/
      tracked_assets.json        # 新闻资产别名注册表
```

各文件职责：

- `models.py`
  - 新闻源配置和标准化文章模型
- `registry/tracked_assets.json`
  - 维护新闻文本里的资产别名命中注册表
  - 只维护“真实文本里明确出现这些别名时应该映射成哪个交易对象”，不生成任何隐含标签
- `sources.py`
  - 默认 feed 列表、分组式来源管理和环境变量扩展加载
- `client.py`
  - 负责下载 RSS / Atom，并解析成统一 `NewsArticle`
  - 同时提供同步和异步抓取接口
- `collector.py`
  - 负责时间筛选、批次去重、条件式 upsert 落库
- `service.py`
  - 模块统一编排入口，包含 scheduler 构建
- `runner.py`
  - 命令行运行入口
  - 支持 `--list-sources`、`--print-coverage` 和 `--print-context`

## 去重与更新策略

当前去重键：

- `url_hash`

URL 规范化策略：

- 解析相对链接，并基于 `feed_url` 转成绝对 URL
- 只接受 `http / https` 链接，过滤 `mailto:`、`javascript:` 这类非文章地址
- 移除常见追踪参数，例如 `utm_*`、`fbclid`、`gclid`
- 对不同 query key 做稳定排序，降低同文不同序参数导致的重复，同时保留重复 key 的原始顺序
- 去掉 fragment，统一 host 大小写和默认端口

落库策略：

- 新文章直接插入
- 同一批次内先按 `url_hash` 去重，并优先保留正文更完整的版本
- 已存在文章按 `url_hash` 比较标准化结果
- 只有标题、正文、标签、命中币种、图片、原始 payload 等字段发生变化时才更新
- 如果后续某次 feed 返回的信息更稀疏，不会把已有摘要、正文、作者、图片、外部 ID 冲掉
- 完全相同的重复新闻会跳过更新，避免定时任务反复无差别写库

这样可以兼容：

- 同一 feed 重复推送
- 文章标题被源站二次编辑
- 正文摘要在首次发布后被补全

## 解析与时间过滤细节

- Atom 链接优先使用 `rel="alternate"`，正文页链接优先级高于 `self`
- Atom `summary` / `content` 支持 XHTML 结构，不再静默丢失嵌套正文
- `source_type` 不再统一写死为 `rss`
- 时间窗口过滤优先使用 `published_at`，为空时回退到 `collected_at`
- `source_names=None` 表示“按默认源全量抓取”，空列表表示“本轮不抓取任何源”
- 现在也支持按 `source_group / category / tag` 过滤来源，方便按采集面组织任务

## 采集覆盖检查

当前模块会把每个 source 的采集结果写入数据库表 `collection_runs`，用于回答下面这些运维问题：

- 哪些源最近成功采集过
- 哪些源最近连续失败或进入冷却
- 最近一次采集拉回了多少条原始文章
- 某个源是不是长时间没有新样本

查看覆盖情况：

```bash
python -m data_layer.news_data.runner --print-coverage
```

查看给 AI 直接消费的最近新闻上下文：

```bash
python -m data_layer.news_data.runner --print-context --hours 24
```

按分组查看覆盖情况：

```bash
python -m data_layer.news_data.runner --print-coverage --groups core_media
```

覆盖报告现在不只返回计数，还会补齐面向 AI 的质量语义：

- `configuration_ready`
  - 当前源是否存在可用 `feed_url / fallback_feed_urls`
- `health_status`
  - `ready / stale / cooldown / error / empty / missing / unconfigured / disabled`
- `is_ready_for_ai`
  - 当前这一路新闻是否适合作为 AI 直接消费的文本证据
  - `health_status=ready` 只表示 source 近期可运行；对于 `core_media / market_intelligence`，现在除了要求最近窗口内达到 `recommended_recent_articles` 阈值，还要求最近文章里至少有资产标签命中，且连续新闻流的正文覆盖率不能太薄，才会被标成 `is_ready_for_ai=true`
- `data_quality_flags`
  - 结构化质量标记，例如 `no_recent_articles / recent_articles_thin / source_in_cooldown / stale_source`
- `quality_notes`
  - 给维护者和后续 AI 的解释性说明
- `coverage_expectation`
  - 区分 `continuous_newsflow` 和 `event_driven_reference`
- `recommended_recent_articles`
  - 连续新闻流在当前 `hours` 窗口内建议至少有多少篇新增文章
- `recent_article_ratio / has_recent_article / last_article_age_seconds`
  - 进一步描述这个源最近是否真的在产出可用文本
- `recent_articles_with_content_text / recent_articles_with_relevance_symbols`
  - 进一步描述最近窗口里有多少文章真正带正文和资产映射
- `recent_content_text_coverage_ratio / recent_relevance_symbol_coverage_ratio`
  - 最近窗口里正文和资产命中覆盖比例

除了 source coverage，现在 `load_latest_context_bundle()` 还会输出最近新闻窗口的 AI 上下文聚合结果：

- `as_of`
  - 最近一篇文章的有效时间
- `raw_as_of`
  - 最近一篇真实已落库文章的有效时间，不管它是否达到 AI-ready 门槛
- `source_counts`
  - 最近窗口里每个 AI-ready 来源贡献了多少篇文章
- `raw_article_count / raw_source_counts`
  - 最近窗口里全部真实已落库文章和来源数量，不把未达标来源伪装成“没有数据”
- `ai_ready_source_names / ai_excluded_source_names / ai_excluded_sources`
  - 明确告诉维护者哪些来源真正进入了 AI 直读视图，哪些来源虽然有真文章但被质量门槛挡在外面
- `coverage_summary`
  - 当前 ready/problem source 数量、`ready_for_ai_source_count / not_ready_for_ai_source_count`、缺失了哪些真正达到 AI 可用门槛的高频新闻分组，以及 `coverage_by_source` 摘要
- `configured_universe_summary`
  - 基于 `registry/tracked_assets.json` 输出当前默认新闻跟踪资产宇宙
  - 会显式给出 `asset_count / market_role_counts / missing_market_role_groups / breadth_status`
  - 这层只描述“新闻文本命中注册表本身是否够宽”，不会伪造任何未出现的资产新闻
- `source_health_summary`
  - source 总数、ready/problem 数量、stale/cooldown 数量，以及 `ready_for_ai_source_count / not_ready_for_ai_source_count`
- `source_health`
  - 每个来源的 `health_status / recent_articles / cooldown / stale` 状态
- `text_completeness_summary`
  - AI-ready 视图里有多少文章有摘要、正文和资产标签
- `raw_text_completeness_summary`
  - 全部真实已落库文章里的摘要、正文和资产标签覆盖情况
- `category_distribution / source_group_distribution / tag_distribution`
  - AI-ready 新闻窗口的结构分布
- `dominant_symbols`
  - AI-ready 新闻视图里最常提及的资产和关键稳定币
- `latest_articles`
  - 最近 AI-ready 文章列表，保留标题、链接、时间、来源、标签和资产命中
- `data_quality_flags / quality_notes`
  - 是否存在新闻流过薄、单一来源过度集中、缺核心媒体、缺市场深度解读、正文缺失比例高、或默认跟踪资产宇宙仍过窄等问题

这层 bundle 不会伪造“情绪值”或“市场判断”，只会把真实新闻窗口整理成更适合 AI 读取的上下文结构。

如果最近窗口里确实已经有新闻，但这些新闻全部来自尚未达到 `is_ready_for_ai=true` 的来源，那么 bundle 会出现下面这种正常结果：

- `article_count = 0`
- `raw_article_count > 0`
- `latest_articles = []`
- `ai_excluded_sources` 里保留被挡掉的真实来源和文章覆盖情况

当前新闻覆盖判断有两个重要约束：

- `core_media / market_intelligence` 会被视为连续新闻流
  - 最近窗口内没有新增文章或新增文章数量低于推荐阈值时，即使 `health_status=ready`，也不会被算作 `is_ready_for_ai=true`
  - 最近窗口里如果没有任何资产标签命中，或正文覆盖率过低，也不会被算作 `is_ready_for_ai=true`
  - `load_latest_context_bundle().coverage_summary.missing_high_frequency_source_groups` 现在按 `is_ready_for_ai` 计算，而不是按技术上的 `ready` 计算，避免把“源还活着但新闻太薄”误当成已经覆盖
- `ecosystem / governance_forum / research_security_regulatory` 会被视为低频参考流
  - 这类源没有最近文章不一定是采集异常；只要 source 仍然可运行并且历史样本可用，仍可保留 `is_ready_for_ai=true`
  - coverage 会明确提示“当前没有新增公告类证据”，避免 AI 误以为所有新闻流都同样活跃

- 模块内部仍使用“无 tzinfo 的 UTC 时间”以兼容当前 SQLite 存储格式，但已移除 `datetime.utcnow()` 的弃用写法

## 当前配置项

环境变量：

- `NEWS_INTERVAL_SECONDS`
  - 调度频率，默认 `300`
- `NEWS_TIMEOUT_SECONDS`
  - 单次请求超时，默认 `20`
- `NEWS_FETCH_CONCURRENCY`
  - 并发抓取多少个源，默认 `8`
- `NEWS_MAX_CONNECTIONS_PER_HOST`
  - 单 host 最大并发连接数，默认 `4`
- `NEWS_RESOLVER_MODE`
  - `threaded / async / auto`，默认 `auto`
- `NEWS_SOURCE_FAILURE_THRESHOLD`
  - 同一新闻源连续失败多少轮后进入冷却期，默认 `2`
- `NEWS_SOURCE_COOLDOWN_BASE_SECONDS`
  - 首次熔断冷却时长，默认 `300`
- `NEWS_SOURCE_COOLDOWN_MAX_SECONDS`
  - 熔断冷却最大时长，默认 `3600`
- `NEWS_MAX_ITEMS_PER_SOURCE`
  - 每个源最多解析多少条，默认 `50`
- `NEWS_LOOKBACK_HOURS`
  - 默认只保留最近多少小时内的新闻，默认 `72`
- `NEWS_USER_AGENT`
  - 新闻请求头
- `NEWS_EXTRA_FEEDS_JSON`
  - 追加新闻源，JSON 数组格式

`NEWS_EXTRA_FEEDS_JSON` 例子：

```json
[
  {
    "name": "Example Feed",
    "feed_url": "https://example.com/feed.xml",
    "fallback_feed_urls": ["https://backup.example.com/feed.xml"],
    "category": "research",
    "source_group": "custom",
    "language": "en",
    "enabled": true,
    "tags": ["research", "macro"]
  }
]
```

## 当前默认源明细

当前内置 57 个公开 RSS / Atom 源，按用途分组如下：

| 名称 | 类型 | 说明 |
| --- | --- | --- |
| CoinDesk | `crypto-news` | 主流加密新闻媒体，更新频率高 |
| Cointelegraph | `crypto-news` | 覆盖市场、政策和项目动态 |
| Decrypt | `crypto-news` | 偏新闻和政策话题 |
| CryptoSlate | `crypto-news` | 新闻结合币种与项目数据上下文 |
| BeInCrypto | `crypto-news` | 覆盖面广，适合补充长尾新闻 |
| NewsBTC | `crypto-news` | 偏比特币和市场类内容 |
| AMBCrypto | `crypto-news` | 覆盖山寨币、链上热点和短周期市场话题 |
| CryptoPotato | `crypto-news` | 偏快讯和市场分析，更新较快 |
| CoinJournal | `crypto-news` | 兼顾新闻、行情和项目动态 |
| Blockworks | `market-intelligence` | 更偏机构视角、市场结构与研究 |
| Bitcoin Magazine | `market-intelligence` | 偏比特币生态与长期叙事 |
| The Defiant | `market-intelligence` | 偏 DeFi、链上资本市场和协议层事件 |
| 99Bitcoins | `market-intelligence` | 偏比特币教育内容和交易叙事补充 |
| Arbitrum | `ecosystem` | 官方生态博客，适合跟踪 L2 产品、升级和生态方向 |
| Chainlink Blog | `ecosystem` | 官方预言机生态博客，适合跟踪数据基础设施与集成动态 |
| Sui Blog | `ecosystem` | 官方生态博客，适合跟踪 Sui 生态、协议和产品演进 |
| Sonic Blog | `ecosystem` | 官方生态博客，适合补 Sonic 主网路线、研究与性能演进 |
| Sei Blog | `ecosystem` | 官方生态博客，适合补 Sei 公告、EVM 演进和生态动态 |
| Lido Blog | `ecosystem` | 官方质押生态博客，适合补 ETH 质押、节点运营和协议治理动态 |
| 1inch Blog | `ecosystem` | 官方 DeFi 聚合器博客，适合补交易路由、产品更新和链上执行话题 |
| Synthetix Blog | `ecosystem` | 官方衍生品协议博客，适合补永续合约、路线图和系统迁移动态 |
| EigenLayer Blog | `ecosystem` | 官方 restaking 生态博客，适合补再质押、AVS 和协议方向变化 |
| SatLayer Blog | `ecosystem` | 官方比特币再质押生态博客，适合补 BTC 质押、BVS 与奖励机制动态 |
| Avail Blog | `ecosystem` | 官方模块化基础设施博客，适合补 DA、跨链桥与多链应用方向变化 |
| Celestia Blog | `ecosystem` | 官方模块化数据可用性博客，适合补模块化链与 DA 方向变化 |
| RedStone Blog | `ecosystem` | 官方预言机博客，适合补预言机设计、数据基础设施和 OEV 话题 |
| QuickNode Blog | `ecosystem` | 区块链基础设施博客，适合补 RPC、Solana 性能和链上开发基础设施变化 |
| Lido Research | `governance` | Lido 治理论坛，适合补质押参数、研究提案和社区治理动态 |
| EigenLayer Forum | `governance` | EigenLayer 治理论坛，适合补 AVS、再质押风险和治理争议 |
| Arbitrum Forum | `governance` | Arbitrum 官方论坛，适合补 DAO 提案、基金计划和生态治理动态 |
| ENS Governance | `governance` | ENS DAO 论坛，适合补身份协议治理、资金提案和社区周报 |
| Sky Forum | `governance` | Sky 论坛，适合补稳定币、跨链桥和协议参数治理动态 |
| dYdX Forum | `governance` | dYdX 社区论坛，适合补激励提案、永续交易治理和链上参数变化 |
| Safe Forum | `governance` | Safe 社区论坛，适合补钱包治理、产品反馈和多签运维相关讨论 |
| Starknet Community | `governance` | Starknet 社区论坛，适合补 SNIP 提案、质押参数和 L2 治理动态 |
| CoW DAO Forum | `governance` | CoW DAO 论坛，适合补 grants、治理提案和 DEX 协议方向变化 |
| Gitcoin Governance | `governance` | Gitcoin 治理论坛，适合补 grants、公共物品资助和社区治理讨论 |
| Osmosis Community Hall | `governance` | Osmosis 社区论坛，适合补 Cosmos 生态治理、白名单提案和应用链基础设施动态 |
| Celestia Forum | `governance` | Celestia 论坛，适合补模块化生态项目、治理讨论和 DA 相关提案 |
| Zcash Community Forum | `governance` | Zcash 社区论坛，适合补隐私币治理、资助申请和社区政策讨论 |
| Babylon Forum | `governance` | Babylon 论坛，适合补比特币质押、跨生态流动性和社区治理讨论 |
| Polkadot Forum | `governance` | Polkadot 论坛，适合补中继链治理、技术委员会和多链生态治理议题 |
| Cosmos Hub Forum | `governance` | Cosmos Hub 论坛，适合补 ATOM 社区治理、Hub 方向和 Cosmos 生态争议讨论 |
| Nym Forum | `governance` | Nym 社区论坛，适合补隐私网络治理、社区实验和 NYM 生态方向变化 |
| Berachain Forum | `governance` | Berachain 论坛，适合补 BRIP 提案、PoL 参数和 L1 升级治理动态 |
| Scroll Forum | `governance` | Scroll 治理论坛，适合补 zkEVM、安全评估和 Rollup 升级相关讨论 |
| Initia Forum | `governance` | Initia 论坛，适合补 IBC 限额、链升级和 Cosmos 互操作相关提案 |
| Aztec Forum | `governance` | Aztec 论坛，适合补隐私执行环境、grant 提案和 Noir 生态安全讨论 |
| Connext Forum | `governance` | Connext 社区论坛，适合补跨链桥治理、迁移提案和互操作生态方向变化 |
| Pyth DAO Forum | `governance` | Pyth DAO 论坛，适合补预言机参数、跨链 signer 更新和提案执行动态 |
| Chainalysis | `research` | 偏链上调查、执法、合规与安全事件 |
| Immunefi | `security-research` | 偏漏洞赏金、安全事件和审计协作动态 |
| SEC Press Releases | `regulatory` | 官方监管公告源，适合跟踪执法、ETF、政策口径变化 |
| Elliptic | `research` | 偏链上取证、反洗钱、制裁与合规研究 |
| CFTC General Press Releases | `regulatory` | 官方监管公告源，适合跟踪衍生品监管和政策表态 |
| CFTC Enforcement Actions | `regulatory` | 官方执法公告源，适合跟踪处罚、诉讼和违规事件 |
| Trail of Bits | `security-research` | 偏安全审计、漏洞分析和工程安全研究 |

如果后续要继续扩源，建议优先满足下面几个约束：

- 有稳定公开的 RSS / Atom，而不是只能抓网页
- 文章 URL 稳定，便于 `url_hash` 去重
- 内容和加密市场强相关，而不是泛科技站点
- 最好能补齐不同信息视角，而不是重复堆叠同类媒体

## 当前资产命中注册表

新闻模块现在把资产别名注册表独立放在：

- `data_layer/news_data/registry/tracked_assets.json`

这样后续如果要扩充 AI 关注的交易对象，不需要改解析器主体逻辑，只需要维护注册表。

当前注册表维护原则：

- 只收录真实市场中对交易分析有价值的资产或稳定币
- 优先收录默认新闻源高频提到、且对当前市场结构判断有意义的对象
- 对容易和普通英文词冲突的 ticker，优先使用更明确的项目全名别名
  - 例如 `LINK` 优先匹配 `Chainlink`
  - `OP` 优先匹配 `Optimism`
  - `ARB` 优先匹配 `Arbitrum`

当前 `_extract_symbols()` 还按文本里首次出现顺序返回命中对象，而不是按注册表固定顺序返回。这样下游 AI 读取最近文章时，更容易保持原始语义顺序。

`load_latest_context_bundle()` 现在也会基于这份注册表补充 `configured_universe_summary`。如果默认注册表只覆盖很少几个核心资产、缺稳定币或缺生态 beta 资产，bundle 会直接打出 `news_configured_market_breadth_limited`，提醒维护者当前新闻流更像“窄观察名单”，而不是可代表更广市场 breadth 的文本映射层。

## 当前网络层优化

这版对 `news_data` 的下载层做了两类稳健性增强，重点是适配代理链路和不稳定 feed：

- 显式使用 `aiohttp.TCPConnector`
- 默认保持 `aiohttp` 原生 `auto resolver`
- 同时暴露 `NEWS_RESOLVER_MODE`，必要时可以切到 `threaded` 或 `async`
- 增加总并发和单 host 并发上限，避免一次性对几十个源同时建连
- 新闻源支持 `fallback_feed_urls`
- 重试时会在主地址和备用地址之间轮转，避免对同一个异常 URL 连续重压
- 连续失败的新闻源会进入进程内冷却期，避免每轮调度都重复撞同一个坏源
- 解析与落库时会记录本轮实际使用的 feed 地址，而不是强行写死主地址

这次修复里，`CoinDesk` 已改成更少重定向的 canonical URL：

```text
https://www.coindesk.com/arc/outboundfeeds/rss
```

同时保留了备用地址，避免在某些代理 / 证书 / 重定向异常下整源失效。

需要注意：

- 如果代理链路本身不稳定，某些源仍然可能出现 `Connection reset by peer`、`ssl:default [None]` 或证书相关异常
- 现在这些异常会被限制在单个 source 内部处理，不会影响其他新闻源继续抓取
- 排障时优先看日志里的 `候选x/y` 和 `url=...`，可以快速确认是主地址失败还是备用地址也一起失败
- 熔断状态保存在 `NewsFeedClient` 进程内内存里，因此长期 `scheduler` 模式会自动生效，单次 `once` 模式结束后不会保留状态

当前这 57 个源覆盖的输入结构大致是：

- 高频媒体流：适合做事件触发、新闻时间序列和标题级情绪特征
- DeFi / 叙事流：适合补协议层、生态轮动和赛道热度变化
- 官方生态流：适合补协议升级、主网公告、生态项目推进、开发者基础设施方向
- 治理论坛流：适合补 DAO 提案、参数调整、论坛争论、激励治理以及跨链 / 隐私 / Cosmos / zk / 预言机生态治理预期变化
- 研究 / 安全 / 合规流：适合补安全事件、审计研究、监管事件、执法动作和链上调查类信号

如果后面你要进一步做 AI 量化，建议下一批优先补：

- 交易所公告源
- 安全机构 / 审计机构源
- 宏观与 ETF / 监管专题源
- 更多目标币种官方博客源

## 运行方式

执行一次采集：

```bash
python -m data_layer.news_data.runner --mode once
```

只保留最近 24 小时新闻：

```bash
python -m data_layer.news_data.runner --mode once --hours 24
```

只跑指定新闻源：

```bash
python -m data_layer.news_data.runner --mode once --sources CoinDesk,Cointelegraph
```

按来源组运行：

```bash
python -m data_layer.news_data.runner --mode once --groups ecosystem
```

列出当前新闻源：

```bash
python -m data_layer.news_data.runner --list-sources --groups research_security_regulatory
```

启动长期调度：

```bash
python -m data_layer.news_data.runner --mode scheduler
```

调度器默认行为：

- 每次定时任务使用独立的数据库连接，避免 APScheduler 工作线程复用主线程 SQLite 连接
- `max_instances=1`，避免采集任务重叠执行
- `coalesce=True`，进程卡顿恢复后合并积压触发
- `misfire_grace_time` 至少 60 秒，避免短时阻塞导致任务直接丢失
- 下载层会按 URL 级别轮转重试，主地址异常时自动尝试备用 feed URL
- 如果代理环境对默认 DNS 路径不稳定，可以通过 `NEWS_RESOLVER_MODE` 切换 resolver 实现
- 同一 source 连续失败达到阈值后会暂时跳过，冷却时间按指数退避增长，避免坏源长期占用采集窗口

## 异步接入示例

如果后面你把这个模块接到异步 Web 服务里，优先使用异步入口：

```python
from data_layer.news_data.service import NewsDataService

service = NewsDataService()
service.init_storage()

articles = await service.collect_once_async(hours=24, source_names=["CoinDesk"])
```

同步入口 `collect_once()` / `fetch_articles()` 仍然保留，但不应该在已有事件循环里直接调用。

## 后续建议

这个模块现在是“新闻原始数据层”。如果你的目标是做 AI 量化，下一步建议在逻辑处理层新增：

- 新闻情绪分析
- 事件类型识别
- 新闻与目标币种映射增强
- 新闻时效衰减特征
- 新闻和价格/成交量联动特征

也就是说，`news_data` 先负责把新闻稳定存下来，后续的“能不能交易、怎么交易”再交给逻辑层。 
