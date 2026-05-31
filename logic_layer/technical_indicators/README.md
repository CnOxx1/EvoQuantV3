# 技术指标模块 `technical_indicators`

## 模块定位

这个模块属于逻辑处理层，负责把多个交易所的 K 线合并成统一的主时间序列，再计算技术指标并写回数据库。

当前处理对象：

- 交易所：Binance、OKX、Bybit
- 交易对：`BTC/USDT`、`ETH/USDT`、`SOL/USDT`、`SUI/USDT`
- 输入表：`klines`
- 输出表：`merged_klines`、`technical_indicators`

现在 `technical_indicators` 不再只是“纯技术指标表”，也同时承载了给 AI 使用的市场上下文特征：

- `ticker` 聚合特征
- `funding` 聚合特征
- `orderbook` 聚合特征

但从整个项目的 AI 供数结构看，`technical_indicators` 仍然只是其中一层。完整分析还应该结合 `logic_layer.exchange_comparison` 的横截面执行语境、`logic_layer.macro_context` 的宏观背景，以及 `data_layer.news_data` 的文本事件输入。

## AI 文档维护约束

这份 README 是后续 AI 开发和维护 `technical_indicators` 时的工作文档，不只是功能介绍。

后续如果有 AI 修改了下面任一内容，必须同步更新当前 README：

- 模块代码树、文件职责或运行入口
- 指标集合、聚合逻辑、并表逻辑、输入输出表或时间窗口
- AI 可消费特征范围、上下游依赖关系或实现边界
- 当前测试覆盖或推荐扩展方向

## 快速导航

- [整体方案](#整体方案)
- [模块代码树](#模块代码树)
- [计算实现说明](#计算实现说明)
- [多交易所K线合并方法](#多交易所k线合并方法)
- [当前已实现的技术指标](#当前已实现的技术指标)

## 整体方案

建议路径分三步：

1. 从 `klines` 读取同一 `symbol + timeframe + open_time` 的多交易所 K 线。
2. 先合并成统一主 K 线，再基于统一主 K 线计算技术指标。
3. 再把 `ticker / funding / orderbook` 作为市场上下文，通过时间对齐并入同一行特征。

这样做的原因：

- 避免三个交易所各算一套指标，后面策略层不好统一。
- 降低单一交易所异常针、流动性偏差对指标的干扰。
- 为后续 AI 训练提供更稳定的一致输入。
- 让 AI 同时看到趋势、波动、流动性、资金费率和盘口结构。
- 增量刷新时不必再扫描全部高频快照历史，能更稳定地长期运行。

## 模块代码树

下面代码树省略 `__pycache__` 等缓存目录，只保留维护这个模块最常用的源码文件：

```text
logic_layer/
  README.md                      # 逻辑层总览文档
  technical_indicators/
    README.md                    # 模块说明、指标范围与维护约束
    __init__.py                  # 模块包入口
    aggregator.py                # 多交易所 K 线聚合
    calculator.py                # 技术指标与统计特征计算
    enricher.py                  # ticker / funding / orderbook 并表
    repository.py                # 输入读取与结果落库
    service.py                   # 全量/增量刷新编排
    runner.py                    # CLI 运行入口
    utils.py                     # 时间周期与窗口工具
```

各文件职责：

- `aggregator.py`
  - 多交易所 K 线聚合为统一主 K 线
- `calculator.py`
  - 技术指标计算
- `enricher.py`
  - 将 `ticker / funding / orderbook` 按时间对齐后并入特征行
- `repository.py`
  - 读写 `klines / merged_klines / technical_indicators / tickers / funding_rates / orderbook_snapshots`
  - 对上下文快照按增量计算窗口限界读取，并为每个交易所保留窗口前最后一条锚点样本
- `service.py`
  - 模块统一编排，负责全量/增量刷新
- `utils.py`
  - 时间周期与窗口换算工具

## 计算实现说明

当前 `calculator.py` 已改成“分块构造 DataFrame”的形式，而不是连续对同一个 `DataFrame` 做大量 `frame["col"] = ...` 赋值。

当前实现流程：

- 先保留基础列：`symbol / timeframe / open_time / close / volume`
- 再统一预计算共享中间序列，例如 `delta / true_range / typical_price / rolling_std`
- 按类别分别构造小块特征表：`trend / momentum / volatility / volume / structure / state / risk / crossover / pivot / pattern / adaptive / microstructure`
- 最后用一次 `concat` 合并成结果表

这样做的好处：

- 避免 pandas `DataFrame is highly fragmented` 性能告警
- 新增指标时更容易按类别扩展
- 共享中间变量更清晰，减少重复计算和重复赋值
- 后续如果继续拆成子计算器，也更容易演进

这次在分块结构上又继续扩了一批特征，重点补到这几类：

- 趋势强度与相对位置：`ADXR / DMI Oscillator / Price-to-MA / Ichimoku Cloud Width & Position`
- 动量补充：`RSI(28) / SMI(14, 3, 3)`
- 波动估计：`True Range % / Normalized Range / Historical Volatility / Chaikin Volatility / Keltner Width`
- 成交量斜率与价量关系：`OBV Slope / ADL Slope / Price-to-VWMA / Volume-Price Correlation`
- K线结构：`Candle Body % / Upper & Lower Shadow % / CLV / Intrabar Trend Efficiency`
- 状态持续性：`Positive Return Ratio / Return Autocorr / Volume Autocorr / Range Percent Rank`

## 多交易所K线合并方法

当前默认方法：`volume_weighted_ohlc_v1`

- `open`：按成交量加权平均
- `close`：按成交量加权平均
- `high`：取三家交易所最高值
- `low`：取三家交易所最低值
- `volume`：三家交易所成交量求和
- `exchange_count`：参与本根K线合并的交易所数量
- `source_exchanges`：参与合并的交易所列表

说明：

- 这种方式比直接选单一交易所更稳。
- 如果某一时刻只有部分交易所有数据，也允许用可用数据合并，并记录 `exchange_count`。
- 后续如果你要做更严格的指数价格，可以扩展成“按 quote 成交额加权”或“异常值剔除后加权”。

## 当前已实现的技术指标

当前模块已经不再停留在第一版基础指标，而是扩展成更适合 AI 特征工程和策略过滤的指标集合，覆盖趋势、动量、波动、量价锚定、趋势结构、压缩状态、市场状态、分位状态、风险调整、交叉信号、枢轴点、蜡烛形态、自适应/Ehlers 和微观结构统计等方向。当前共计 **228 个技术指标**。

### 趋势类

- `SMA(5, 10, 20, 60)`
- `SMA(120)`
- `EMA(7, 20, 50, 100)`
- `DEMA(20)`
- `TEMA(20)`
- `HMA(21)`
- `ZLEMA(20)`
- `KAMA(10, 2, 30)`
- `EMA20 Slope(5)`
- `SMA20 Slope(5)`
- `Price to SMA20 / SMA60`
- `Price to EMA20 / EMA50`
- `MACD(12, 26, 9)`
- `MACD Hist Z-Score(20)`
- `PPO(12, 26, 9)`
- `Supertrend(10, 3)`
- `Parabolic SAR(0.02, 0.2)`
- `Linear Regression Slope(20)`
- `Linear Regression R2(20)`
- `Regression Distance(20)`
- `Ichimoku(Tenkan, Kijun, Senkou A/B)`
- `Ichimoku Cloud Width / Position`
- `Price to Kijun(26)`
- `Aroon Up / Down / Oscillator(25)`

用途：

- 判断短中期趋势方向
- 判断金叉死叉
- 判断价格偏离均线的幅度
- 判断长期趋势过滤和云层支撑阻力
- 判断趋势斜率和趋势持续性
- 判断价格相对趋势锚点和云层的相对位置

### 动量类

- `RSI(14)`
- `RSI(28)`
- `Stoch RSI(14, 3, 3)`
- `KDJ(9, 3, 3)`
- `SMI(14, 3, 3)`
- `ROC(12)`
- `Momentum(10)`
- `RMI(14, 5)`
- `CFO(20)`
- `Awesome Oscillator(5, 34)`
- `Accelerator Oscillator(5, 34)`
- `PFE(10)`
- `Williams %R(14)`
- `TSI`
- `Schaff Trend Cycle(10, 23, 50)`
- `TRIX(30)`
- `DPO(20)`
- `Fisher Transform(9)`
- `Coppock Curve(11, 14, 10)`
- `Coppock Signal(10)`
- `KST`
- `Qstick(10)`
- `DeMarker(14)`
- `RVI(10)`
- `CMO(14)`
- `Ultimate Oscillator(7, 14, 28)`

用途：

- 判断超买超卖
- 判断动量拐点
- 配合趋势过滤假突破
- 判断价格加速度是否衰减
- 判断多周期动量是否共振

### 波动类

- `Bollinger Bands(20, 2)`
- `Bollinger %B`
- `ATR(14)`
- `True Range %`
- `Normalized Range(14)`
- `ATR%`
- `Historical Volatility(20)`
- `Parkinson Volatility(20)`
- `Garman-Klass Volatility(20)`
- `Rogers-Satchell Volatility(20)`
- `Chaikin Volatility(10)`
- `Keltner Channel(20, ATR*2)`
- `Keltner Width(20)`
- `Donchian Channel(20)`
- `Donchian Width(20)`
- `Donchian Position(20)`
- `Choppiness Index(14)`
- `Relative Volatility Index(14)`
- `Squeeze On/Off(20)`
- `Mass Index(25)`
- `Ulcer Index(14)`
- `Rolling Drawdown(20)`

用途：

- 判断波动扩张/收缩
- 给止损、止盈和仓位动态调参
- 判断突破通道和波动压缩
- 判断价格在通道中的位置和近期回撤

### 趋势强度类

- `ADX(14)`
- `ADXR(14)`
- `+DI(14)` / `-DI(14)`
- `DMI Oscillator(14)`
- `Vortex + / -(14)`
- `Efficiency Ratio(10)`
- `VHF(28)`
- `Bull Power(13)`
- `Bear Power(13)`

用途：

- 判断当前是否适合趋势策略
- 区分“有方向”还是“震荡”

### 分位与状态类

- `Price Percent Rank(20)`
- `Volume Percent Rank(20)`
- `ATR Percent Rank(20)`
- `Range Percent Rank(20)`
- `Volume Z-Score(20)`

用途：

- 判断当前价格、成交量、波动所处的历史相对位置
- 适合作为 AI 的归一化状态特征
- 便于识别极端扩张、极端冷清和异常活跃阶段

### K线结构与位置类

- `Candle Body %`
- `Upper Shadow %`
- `Lower Shadow %`
- `Body to Range Ratio`
- `Close Location Value`
- `Intrabar Trend Efficiency`

用途：

- 判断单根 K 线内部多空结构
- 区分“实体推动”与“影线噪声”主导
- 给 AI 提供比单纯涨跌幅更细的蜡烛图形态特征

### 风险调整与收益质量类

- `Downside Deviation(20)`
- `Upside Deviation(20)`
- `Sharpe-like(20)`
- `Sortino-like(20)`
- `Calmar-like(20)`
- `Gain-to-Pain Ratio(20)`
- `Median Return(20)`
- `MAD Return(20)`
- `Return IQR(20)`
- `Tail Ratio(20)`
- `Positive Return Ratio(20)`
- `Return Autocorr(20)`
- `Volume Autocorr(20)`
- `Return Skew(20)`
- `Return Kurtosis(20)`

用途：

- 判断最近收益是否匹配相应波动和下行风险
- 判断上涨收益质量、尾部结构和回撤承受能力
- 适合作为 AI 的收益质量和风险收益比特征
- 判断收益和成交量状态是否具备短期持续性

### 成交量与确认类

- `OBV`
- `OBV Slope(20)`
- `ADL`
- `ADL Slope(20)`
- `Chaikin Oscillator`
- `VWMA(20)`
- `Price to VWMA(20)`
- `Rolling VWAP(20)`
- `Rolling VWAP Deviation(20)`
- `Balance of Power`
- `Price Volume Trend`
- `NVI`
- `PVI`
- `KVO`
- `Ease of Movement(14)`
- `Volume Oscillator(5, 20)`
- `Volume-Price Correlation(20)`
- `PVO(12, 26, 9)`
- `MFI(14)`
- `CMF(20)`
- `Force Index(13)`
- `Volume Ratio(20)`
- `return_1` / `return_5` / `return_20`
- `volatility_20`
- `Price Z-Score(20)`

用途：

- 用成交量确认价格趋势
- 给 AI 和策略层提供更直接的收益率与波动率特征
- 判断量价背离和资金流入流出强弱
- 判断趋势是否由真实成交推动

### 交叉信号与多周期关系类

- `EMA Cross 7/20` — EMA 7/20 交叉方向 (1=金叉, -1=死叉, 0=无交叉)
- `EMA Cross 20/50` — EMA 20/50 交叉方向
- `SMA Cross 10/60` — SMA 10/60 交叉方向
- `MACD Cross Signal` — MACD 与信号线交叉方向
- `Price Above EMA Count` — 价格在 EMA 7/20/50/100 之上的数量 (0-4)
- `MA Alignment Score` — MA 排列评分 (-1~+1)
- `Ichimoku Signal` — Ichimoku 综合信号 (-2~+2)
- `Trend Consistency 20` — 20 周期 close>EMA20 比率

用途：

- 给 AI 提供直接可用的交叉事件信号，无需自行判断
- 判断多条均线是否形成多头/空头排列
- 判断趋势一致性和多周期共振程度
- 适合作为策略触发条件和趋势过滤特征

### 枢轴点与支撑阻力类

- `Pivot Classic` — (H+L+C)/3
- `Pivot R1` — 阻力位 1
- `Pivot S1` — 支撑位 1
- `Pivot R2` — 阻力位 2
- `Pivot S2` — 支撑位 2
- `Distance to Pivot %` — 价格与枢轴距离百分比

用途：

- 给 AI 提供经典的日内支撑阻力参考
- 判断价格相对关键价位的距离
- 适合作为止盈止损和仓位管理的参考特征

### 蜡烛图形态类

- `Pattern Doji` — 十字星 (1=出现, 0=未出现)
- `Pattern Hammer` — 锤子线 (1=锤子, -1=上吊)
- `Pattern Engulfing` — 吞没形态 (+1=看涨吞没, -1=看跌吞没)
- `Pattern Morning/Evening Star` — 晨星/暮星 (+1/-1)
- `Pattern Three Soldiers/Crows` — 三兵/三鸦 (+1/-1)
- `Pattern Pin Bar` — Pin bar (+1=看涨, -1=看跌)
- `Pattern Inside Bar` — 内包线 (1=出现)
- `Pattern Outside Bar` — 外包线 (1=出现)

用途：

- 给 AI 提供经典蜡烛图形态的结构化识别结果
- 无需 AI 自行从 OHLC 推断形态
- 适合作为反转信号和趋势延续确认特征

### 自适应与 Ehlers 系列类

- `Ehlers Fisher Transform(13)` — Ehlers 版 Fisher 变换
- `Ehlers Instantaneous Trendline` — 瞬时趋势线
- `Ehlers Cyber Cycle` — 网络周期振荡器
- `Ehlers Dominant Cycle Period` — 主导周期长度
- `Adaptive RSI(14)` — 自适应 RSI
- `Fractal Dimension(20)` — 分形维度
- `Hurst Exponent(20)` — Hurst 指数
- `Entropy(20)` — 信息熵

用途：

- 提供自适应于市场周期的指标，比固定参数指标更灵活
- 判断市场是趋势主导还是均值回归主导（Hurst 指数）
- 判断价格序列的复杂度和可预测性（分形维度、信息熵）
- 适合作为 AI 的市场状态分类和策略选择特征

### 高级统计与微观结构类

- `Realized Volatility(10)` — 10 期已实现波动率
- `Yang-Zhang Volatility(20)` — Yang-Zhang 波动率估计
- `Intraday Intensity(20)` — 日内强度
- `Volume Weighted RSI(14)` — 成交量加权 RSI
- `Relative Volume(5)` — 5 期相对成交量
- `Tick Intensity` — 价格变动强度
- `Amihud Illiquidity(20)` — Amihud 非流动性指标
- `Kyle Lambda(20)` — 价格影响系数
- `Return Dispersion(20)` — 收益率离散度
- `Overnight Gap %` — 隔夜跳空百分比

用途：

- 提供比传统波动率更精确的波动估计（Yang-Zhang）
- 判断市场流动性和价格影响成本（Amihud、Kyle Lambda）
- 判断成交量是否异常放大（相对成交量）
- 给 AI 提供微观结构层面的流动性和执行质量特征
- 适合作为仓位管理和执行策略的输入

## 并入的市场上下文特征

### Ticker 聚合特征

- `ticker_last_price_mean`
- `ticker_mid_price_mean`
- `ticker_spread_bps_mean`
- `ticker_quote_volume_24h_sum`
- `ticker_quote_volume_24h_mean`
- `ticker_change_24h_mean`
- `ticker_vwap_24h_mean`
- `ticker_exchange_count`
- `cross_exchange_last_price_std`
- `cross_exchange_last_price_range_bps`

用途：

- 判断跨交易所价格分歧
- 判断当前流动性和交易活跃度
- 给 AI 提供更接近实时市场状态的上下文

### Funding 聚合特征

- `funding_rate_mean`
- `funding_rate_std`
- `funding_basis_bps_mean`
- `funding_exchange_count`

用途：

- 判断合约市场多空拥挤度
- 判断标记价格与指数价格偏离
- 给 AI 提供衍生品市场情绪信号

### OrderBook 聚合特征

- `orderbook_mid_price_mean`
- `orderbook_spread_bps_mean`
- `orderbook_bid_depth_notional_sum`
- `orderbook_ask_depth_notional_sum`
- `orderbook_total_depth_notional`
- `orderbook_depth_imbalance_mean`
- `orderbook_exchange_count`

用途：

- 判断盘口厚度和滑点风险
- 判断买卖盘不平衡
- 给 AI 提供微观结构特征

## 计算方法

### SMA

方法：

- `SMA(n) = 最近 n 根收盘价的简单平均`

### EMA

方法：

- `EMA(n)` 使用指数加权移动平均，越近的数据权重越高

### MACD

方法：

- `EMA12 - EMA26 = macd_line`
- `macd_line` 的 `EMA9 = macd_signal`
- `macd_line - macd_signal = macd_hist`

### PPO(12, 26, 9)

方法：

- `PPO = (EMA12 - EMA26) / EMA26 * 100`
- 再对 `PPO` 做 `EMA9`

### KAMA(10, 2, 30)

方法：

- 先计算效率比 `ER = abs(close - close.shift(10)) / rolling(sum(abs(close.diff)), 10)`
- 再计算快慢平滑系数
- 用递推方式生成自适应均线

用途：

- 横盘时自动变慢，减少噪声
- 趋势明显时自动变快，提升响应速度

### DEMA / TEMA / HMA

方法：

- `DEMA(20)` 使用双重 EMA 组合，降低普通 EMA 滞后
- `TEMA(20)` 使用三重 EMA 组合，进一步降低滞后
- `HMA(21)` 基于加权移动平均构建，更偏平滑且响应更快
- `ZLEMA(20)` 先对价格做零滞后修正，再做 `EMA20`

用途：

- 为 AI 提供同一趋势下不同平滑方式的均线视角
- 适合识别“趋势存在但普通均线偏慢”的场景

### Efficiency Ratio(10)

方法：

- `ER = abs(close - close.shift(10)) / rolling(sum(abs(close.diff)), 10)`

用途：

- 判断价格运动是更接近趋势推进还是来回震荡
- 适合作为 AI 的市场状态过滤特征

### Aroon(25)

方法：

- `Aroon Up` 反映最近最高点距离当前有多近
- `Aroon Down` 反映最近最低点距离当前有多近
- `Aroon Oscillator = Aroon Up - Aroon Down`

### Linear Regression Slope / R2 / Regression Distance(20)

方法：

- 对最近 `20` 根收盘价做线性回归
- `Slope` 使用回归斜率，并按窗口均价归一化成百分比
- `R2` 表示线性趋势拟合程度
- `Regression Distance` 表示当前收盘价相对回归线末端拟合值的偏离比例

用途：

- 判断趋势是否平滑、是否具备线性推进特征
- 适合作为 AI 的趋势质量和偏离度特征

### RSI(14)

方法：

- 先算每根 K 线涨跌额
- 分别对上涨和下跌做 Wilder 平滑
- `RSI = 100 - 100 / (1 + RS)`

### RMI(14, 5)

方法：

- 使用 `5` 周期价格动量代替普通 RSI 的单周期涨跌额
- 再按 Wilder 平滑方式计算相对强弱

用途：

- 比普通 `RSI` 更偏向中短周期动量质量
- 适合过滤单根噪声带来的假超买超卖

### CFO(20)

方法：

- 对最近 `20` 根收盘价做线性回归预测
- `CFO = (close - forecast) / close * 100`

用途：

- 判断当前价格偏离回归预测值的程度
- 适合作为均值回归和偏离修复特征

### Awesome Oscillator(5, 34)

方法：

- 使用 `Median Price = (high + low) / 2`
- `AO = SMA5(Median Price) - SMA34(Median Price)`

用途：

- 观察短周期和长周期中位价格动量差
- 适合判断趋势加速还是减速

### Accelerator Oscillator(5, 34)

方法：

- `AC = AO - SMA5(AO)`

用途：

- 判断动量变化的二阶加速度
- 对短线节奏变化更敏感

### PFE(10)

方法：

- 比较 `10` 周期价格直线距离与真实路径长度
- 再按方向赋正负号，得到 `Polarized Fractal Efficiency`

用途：

- 判断价格运动是高效率单向推进，还是低效率噪声波动
- 很适合作为 AI 的趋势质量特征

### Stoch RSI(14, 3, 3)

方法：

- 先计算 `RSI(14)`
- 再计算 `StochRSI = (RSI - RSI_min14) / (RSI_max14 - RSI_min14)`
- 再做两次 `3` 周期平滑得到 `K / D`

### Bollinger Bands(20, 2)

方法：

- 中轨：`20` 周期 SMA
- 上轨：`SMA20 + 2 * 标准差`
- 下轨：`SMA20 - 2 * 标准差`
- `bb_width = (上轨 - 下轨) / 中轨`

### ATR(14)

方法：

- `TR = max(high-low, abs(high-prev_close), abs(low-prev_close))`
- 对 `TR` 做 `14` 周期 Wilder 平滑得到 `ATR`

### Parkinson / Garman-Klass / Rogers-Satchell Volatility(20)

方法：

- `Parkinson` 基于 `high/low` 对数区间估计波动率
- `Garman-Klass` 结合 `open/high/low/close` 提升效率
- `Rogers-Satchell` 对趋势行情更稳健

用途：

- 提供比普通收益率波动更丰富的 OHLC 波动视角
- 适合给 AI 区分“同样涨跌幅但盘中结构不同”的行情

### Choppiness Index(14)

方法：

- 计算 `14` 周期 `TR` 总和
- 再计算同周期 `最高价 - 最低价`
- `CI = 100 * log10(sum(TR14) / (HH14 - LL14)) / log10(14)`

用途：

- 识别当前更偏趋势还是更偏震荡
- 适合配合趋势类指标做策略开关

### Relative Volatility Index(14)

方法：

- 将上涨波动和下跌波动分开统计
- 对正向和负向价格变化分别计算 `14` 周期波动率
- `RVI = 100 * up_vol / (up_vol + down_vol)`

用途：

- 用波动而不是涨跌幅来衡量多空主导
- 适合识别“上涨更剧烈”还是“下跌更剧烈”

### Squeeze On / Off(20)

方法：

- 使用 `Bollinger Bands(20, 2)` 和 `Keltner Channel(20, ATR*2)` 对比
- `Squeeze On` 表示布林带完全收进 Keltner 通道
- `Squeeze Off` 表示布林带重新扩张到 Keltner 通道之外

用途：

- 识别波动压缩与释放阶段
- 适合给突破策略和 AI 提供“是否临近扩波”的状态特征

### Supertrend(10, 3)

方法：

- 先计算 `ATR10`
- `basic_upper = (high + low) / 2 + 3 * ATR10`
- `basic_lower = (high + low) / 2 - 3 * ATR10`
- 再结合前一根状态递推得到最终轨道和方向

输出字段：

- `supertrend_10_3`
- `supertrend_direction_10_3`

用途：

- 直接提供趋势跟踪和反转信号
- 比单独均线更适合突破后的跟随判断

### KDJ(9, 3, 3)

方法：

- `RSV = (close - 9周期最低价) / (9周期最高价 - 9周期最低价) * 100`
- `K` 为 `RSV` 的平滑值
- `D` 为 `K` 的平滑值
- `J = 3K - 2D`

### ADX(14)

方法：

- 计算 `+DM`、`-DM`
- 平滑得到 `+DI` 和 `-DI`
- `DX = abs(+DI - -DI) / (+DI + -DI) * 100`
- `ADX` 为 `DX` 的平滑值

### Vortex(14)

方法：

- `VM+ = abs(high - prev_low)`
- `VM- = abs(low - prev_high)`
- 分别对 `VM+ / VM-` 做 `14` 周期求和
- 再除以 `TR14` 的求和

输出字段：

- `vortex_plus_14`
- `vortex_minus_14`

### VHF(28)

方法：

- 先计算 `28` 周期内 `最高收盘价 - 最低收盘价`
- 再除以同周期 `sum(abs(close.diff))`

用途：

- 判断价格是在单方向推进，还是在区间内来回噪声波动
- 和 `Choppiness / ADX / Vortex` 组合时很适合做趋势过滤

### Bull / Bear Power(13)

方法：

- 先计算 `EMA13(close)`
- `Bull Power = high - EMA13`
- `Bear Power = low - EMA13`

用途：

- 判断多头和空头相对均衡价的推进能力
- 适合配合趋势跟随或反转策略做压力判断

### TSI

方法：

- 对价格动量做双重 EMA 平滑
- 对绝对动量也做双重 EMA 平滑
- `TSI = 双平滑动量 / 双平滑绝对动量 * 100`

### Schaff Trend Cycle(10, 23, 50)

方法：

- 先计算 `MACD(23, 50)`
- 对 `MACD` 做一次 `10` 周期随机指标变换并平滑
- 再对结果做第二次随机指标变换并平滑

用途：

- 同时结合趋势和周期拐点
- 比普通 `MACD` 更适合短中周期转折识别

### TRIX(30)

方法：

- 对收盘价连续做三次 `EMA30`
- 再计算三重 EMA 的单周期百分比变化

用途：

- 过滤短期噪声
- 更适合观察中周期趋势动量的拐点

### DPO(20)

方法：

- 当前实现使用无未来数据泄漏版本
- `DPO(20) = close.shift(11) - SMA20`

用途：

- 用于度量价格对中周期趋势的偏离
- 作为 AI 的周期振荡补充特征

### KST

方法：

- 使用多组 `ROC(10, 15, 20, 30)`
- 分别做平滑后按 `1:2:3:4` 加权求和得到 `kst_line`
- 再对 `kst_line` 做 `9` 周期均值得到 `kst_signal`

用途：

- 观察中长周期动量是否共振
- 适合识别趋势再启动和趋势衰减

### Qstick(10)

方法：

- `Qstick = SMA(close - open, 10)`

用途：

- 观察最近一段时间 K 线实体整体偏多还是偏空
- 适合给 AI 提供更直接的蜡烛图方向特征

### DeMarker(14)

方法：

- `DeMax = max(high - prev_high, 0)`
- `DeMin = max(prev_low - low, 0)`
- `DeMarker = sum(DeMax, 14) / (sum(DeMax, 14) + sum(DeMin, 14))`

用途：

- 用于识别超买超卖和动量衰减
- 对趋势末端和反转区间有补充价值

### RVI(10)

方法：

- 使用 `close - open` 作为价格活力分子
- 使用 `high - low` 作为区间分母
- 对最近 `4` 根做加权平滑后，再做 `10` 周期均值
- 同时保存 `rvi_signal_4` 作为信号线

用途：

- 判断上涨/下跌是否伴随“收盘强势”
- 适合配合趋势或反转信号一起过滤

### Fisher Transform(9)

方法：

- 使用 `Median Price = (high + low) / 2`
- 先在 `9` 周期内做归一化
- 再做递推平滑和 Fisher 对数变换
- 同时保留前一周期触发线 `fisher_trigger_9`

用途：

- 强化拐点和极值区间的可分性
- 比普通振荡器更适合识别短线反转

### Coppock Curve(11, 14, 10)

方法：

- 计算 `ROC11 + ROC14`
- 再做 `10` 周期加权移动平均

输出字段：

- `coppock_curve_11_14_10`
- `coppock_signal_10`

用途：

- 观察中周期动量修复和趋势再启动
- 适合作为 AI 的复合动量特征

### OBV

方法：

- 收盘价上涨则加上本期成交量
- 收盘价下跌则减去本期成交量
- 不变则保持不变

### ADL / Chaikin Oscillator

方法：

- `ADL` 使用资金流乘数和成交量做累积
- `Chaikin Oscillator = EMA3(ADL) - EMA10(ADL)`

### VWMA(20)

方法：

- `VWMA = rolling(sum(close * volume)) / rolling(sum(volume))`

### Rolling VWAP(20)

方法：

- 用 `Typical Price = (high + low + close) / 3`
- `Rolling VWAP = rolling(sum(Typical Price * volume)) / rolling(sum(volume))`
- `Rolling VWAP Deviation = (close - Rolling VWAP) / Rolling VWAP`

用途：

- 比单纯均线更接近量价重心
- 适合给 AI 提供价格偏离真实成交重心的特征

### Balance of Power

方法：

- `BOP = (close - open) / (high - low)`

用途：

- 判断单根 K 线内部多空谁更占优
- 适合作为短周期微观方向特征

### Volume Oscillator(5, 20)

方法：

- 使用 `5` 周期与 `20` 周期平均成交量的差值
- 再除以 `20` 周期均量，转成百分比

用途：

- 判断当前量能是扩张还是收缩
- 适合辅助突破、趋势确认和异动识别

### PVO(12, 26, 9)

方法：

- 对成交量计算 `EMA12` 和 `EMA26`
- `PVO = (EMA12 - EMA26) / EMA26 * 100`
- 再对 `PVO` 做 `EMA9` 得到信号线

输出字段：

- `pvo_line`
- `pvo_signal`
- `pvo_hist`

用途：

- 提供量能动量，而不是价格动量
- 很适合与 `MACD / PPO` 搭配判断价量同步性

### Price Volume Trend

方法：

- 每根 K 线计算 `close.pct_change * volume`
- 再做累计求和

用途：

- 观察价格变化是否得到成交量确认
- 适合判断量价背离

### NVI / PVI

方法：

- `NVI` 只在成交量下降的周期更新价格变化
- `PVI` 只在成交量上升的周期更新价格变化
- 当前实现都以 `1000` 作为初始值

用途：

- 区分“缩量中的价格趋势”和“放量中的价格趋势”
- 适合辅助判断主导资金行为

### KVO

方法：

- 基于 `high + low + close` 判断趋势方向
- 再结合区间变化和成交量构造 `Volume Force`
- 用 `EMA34 - EMA55` 得到 `kvo_line`
- 再对其做 `EMA13` 得到 `kvo_signal`

用途：

- 观察量能是否支持趋势延续
- 适合和价格动量指标搭配确认趋势强弱

### Ease of Movement(14)

方法：

- 先计算中位价格变化
- 再乘以波动区间，并除以成交量
- 最后做 `14` 周期平滑

用途：

- 判断价格推动是否“轻松”
- 适合识别低阻力上涨或下跌

### CCI(20)

方法：

- `TP = (high + low + close) / 3`
- `CCI = (TP - SMA(TP, 20)) / (0.015 * MeanDeviation(TP, 20))`

### Ultimate Oscillator(7, 14, 28)

方法：

- 计算 `Buying Pressure`
- 计算 `7 / 14 / 28` 周期相对强度
- 按 `4:2:1` 权重合成最终振荡器

### MFI(14)

方法：

- 用 `Typical Price * Volume` 形成资金流
- 分别统计正资金流和负资金流
- 按 RSI 类似方式转换成 `0-100`

### Williams %R(14)

方法：

- `WR = (HH14 - close) / (HH14 - LL14) * -100`

### CMF(20)

方法：

- 先算 `Money Flow Multiplier`
- 再算 `Money Flow Volume`
- `CMF = 20期资金流量总和 / 20期成交量总和`

### Donchian Channel(20)

方法：

- 上轨：`20周期最高价`
- 下轨：`20周期最低价`
- 中轨：上下轨均值

衍生特征：

- `donchian_width_20`
  - 通道宽度相对中轨的比例
- `donchian_position_20`
  - 当前价格位于通道中的相对位置

### Ichimoku

方法：

- `Tenkan = (9期最高价 + 9期最低价) / 2`
- `Kijun = (26期最高价 + 26期最低价) / 2`
- `Senkou A = (Tenkan + Kijun) / 2`
- `Senkou B = (52期最高价 + 52期最低价) / 2`

说明：

- 当前数据库中保存的是未前移版本，方便策略和 AI 在当前时点直接消费，不引入时间对齐复杂度。

### Parabolic SAR(0.02, 0.2)

方法：

- 维护趋势方向、极值点 `EP` 和加速因子 `AF`
- `AF` 从 `0.02` 开始，随着趋势新高/新低逐步增加，最大到 `0.2`
- 每根 K 线递推新的 `SAR` 值，并在反转时重置状态

输出字段：

- `psar`
- `psar_trend`

用途：

- 给策略层提供顺势止损参考
- 给 AI 提供可解释的趋势反转状态

### Price Z-Score(20)

方法：

- `Z = (close - SMA20) / STD20`

### Price / Volume / ATR Percent Rank(20)

方法：

- 在最近 `20` 根窗口内，计算当前值处于历史分布中的百分位
- 当前实现分别对 `close`、`volume`、`atr_14` 计算

输出字段：

- `price_percent_rank_20`
- `volume_percent_rank_20`
- `atr_percent_rank_20`

用途：

- 判断当前价格是否已处于局部高位或低位
- 判断成交量与波动率是否进入异常活跃区间

### Volume Z-Score(20)

方法：

- `Volume Z-Score = (volume - mean20) / std20`

用途：

- 判断当前成交量相对近期分布是否异常放大或缩小
- 比单纯 `volume_ratio` 更适合做异常值识别

### CMO(14)

方法：

- 统计最近 `14` 根上涨幅度总和和下跌幅度总和
- `CMO = (sum_up - sum_down) / (sum_up + sum_down) * 100`

### Force Index(13)

方法：

- `Force Index = EMA13(close.diff * volume)`

### Downside Deviation / Sharpe-like / Sortino-like(20)

方法：

- `Downside Deviation` 只统计负收益的波动
- `Sharpe-like = rolling_mean(return_1, 20) / volatility_20`
- `Sortino-like = rolling_mean(return_1, 20) / downside_deviation_20`

用途：

- 判断近期收益是否由过高波动换来
- 比单纯收益率更适合给 AI 提供收益质量视角

### Return Skew / Return Kurtosis(20)

方法：

- 对最近 `20` 根 `return_1` 计算偏度和峰度

用途：

- 判断收益分布是更偏尖峰厚尾还是更平滑
- 适合给 AI 提供尾部风险和极端波动结构特征

### Rolling Drawdown(20)

方法：

- 取最近 `20` 根收盘价最高值
- `drawdown = close / rolling_max20 - 1`

### Ulcer Index(14)

方法：

- 先计算相对 `14` 周期最高收盘价的回撤百分比
- 再对回撤平方做 `14` 周期均值
- 最后开平方得到 `Ulcer Index`

用途：

- 比普通波动率更聚焦下行痛苦
- 适合给 AI 和风控层提供回撤压力特征

### Mass Index(25)

方法：

- 先计算 `high - low` 的 `EMA9`
- 再对该结果继续做一次 `EMA9`
- `Mass Ratio = EMA9(range) / EMA9(EMA9(range))`
- 对 `Mass Ratio` 做 `25` 周期滚动求和

用途：

- 观察波动结构是否在积累反转风险
- 适合和趋势类指标一起使用，避免只看方向

### EMA / SMA Slope(5)

方法：

- 用 `EMA20` 和 `SMA20` 的 `5` 周期百分比变化近似斜率

### 扩展统计与风险指标

方法：

- `Upside Deviation(20) = sqrt(mean(max(return_1, 0)^2))`
- `Calmar-like(20) = return_20 / abs(最近20根中的最大回撤)`
- `Gain-to-Pain Ratio(20) = sum(正收益) / abs(sum(负收益))`
- `Median Return(20) = rolling median(return_1)`
- `MAD Return(20) = median(abs(return_1 - median(return_1)))`
- `Return IQR(20) = q75(return_1) - q25(return_1)`
- `Tail Ratio(20) = q95(return_1) / abs(q05(return_1))`

用途：

- 把收益分布从“只有均值和标准差”扩展到中位数、分位差、尾部比例和回撤质量
- 更适合给 AI 识别“收益看起来差不多，但尾部结构完全不同”的行情
- 对趋势策略、风控过滤和仓位控制都更有参考价值

### EMA / SMA 交叉信号

方法：

- 比较当前和前一周期的短期/长期均线关系
- 当短期均线从下方穿越长期均线时标记为 `+1`（金叉）
- 当短期均线从上方穿越长期均线时标记为 `-1`（死叉）
- 无交叉时为 `0`

输出字段：

- `ema_cross_7_20`
- `ema_cross_20_50`
- `sma_cross_10_60`
- `macd_cross_signal`

### Price Above EMA Count / MA Alignment Score

方法：

- `Price Above EMA Count`：统计 close 在 EMA7/20/50/100 之上的数量 (0-4)
- `MA Alignment Score`：计算 EMA7>EMA20>EMA50>EMA100 的排列对数，归一化为 -1~+1

### Ichimoku Signal

方法：

- 综合 Tenkan/Kijun 交叉、价格与云层关系、Senkou A/B 相对位置
- 输出 -2~+2 的综合评分

### Trend Consistency(20)

方法：

- 计算最近 20 根中 close > EMA20 的比率

### Pivot Points (Classic)

方法：

- `Pivot = (前根 High + Low + Close) / 3`
- `R1 = 2 * Pivot - Low`
- `S1 = 2 * Pivot - High`
- `R2 = Pivot + (High - Low)`
- `S2 = Pivot - (High - Low)`
- `Distance to Pivot % = (close - Pivot) / Pivot * 100`

### 蜡烛图形态识别

方法：

- `Doji`：实体 < 全K线范围的 10%
- `Hammer`：下影线 > 实体 2 倍，上影线 < 实体 30%
- `Engulfing`：当前实体完全包裹前一根实体，方向相反
- `Morning/Evening Star`：三根组合形态（大跌/小实体/大涨 或反向）
- `Three Soldiers/Crows`：连续三根同方向实体推进
- `Pin Bar`：单根极长影线，实体在一端
- `Inside Bar`：当前 High/Low 完全被前一根包含
- `Outside Bar`：当前 High/Low 完全包含前一根

### Ehlers Fisher Transform(13)

方法：

- 对 `(high + low) / 2` 在 13 周期内做归一化到 -1~+1
- 再做 Fisher 对数变换：`Fisher = 0.5 * ln((1+x)/(1-x))`
- 使用 0.5 * 前值 + 0.5 * 当前值做递推平滑

### Ehlers Instantaneous Trendline

方法：

- 使用 Ehlers 的 IIR 滤波器结构
- 系数 `a = 2.0 / (period + 1)`
- `IT = (a - a²/4) * price + (a²/2) * prev + (1-a)² * prev_IT`

### Ehlers Cyber Cycle

方法：

- 使用高通滤波器去除趋势成分
- 再用带通滤波器提取主导周期振荡

### Ehlers Dominant Cycle Period

方法：

- 对价格做差分后进行零交叉检测
- 用相邻零交叉间距估计瞬时周期
- 做 EMA 平滑得到主导周期长度

### Adaptive RSI(14)

方法：

- 使用 Ehlers Dominant Cycle Period 作为自适应窗口
- 将窗口 clip 在 5~50 之间
- 在该窗口内计算 RSI

### Fractal Dimension(20)

方法：

- 使用 Higuchi 简化方法
- 比较 n 期和 n/2 期的路径长度变化
- `FD = 1 + ln(path_n / path_half) / ln(2)`

### Hurst Exponent(20)

方法：

- 使用 R/S 分析法
- 计算均值偏差累积极差 R 和标准差 S
- `Hurst = ln(R/S) / ln(N)`
- H > 0.5 趋势持续，H < 0.5 均值回归

### Entropy(20)

方法：

- 对最近 20 根收益率做 10 bin 直方图
- 计算 Shannon 信息熵：`H = -sum(p * log2(p))`
- 归一化到 0~1

### Realized Volatility(10)

方法：

- `RV = sqrt(sum(return_1², 10))`

### Yang-Zhang Volatility(20)

方法：

- 结合 overnight（开盘跳空）方差、open-to-close 方差和 Rogers-Satchell 方差
- `YZ = sqrt(overnight_var + k * oc_var + (1-k) * rs_var)`
- 比单一估计方法更高效且无偏

### Intraday Intensity(20)

方法：

- `II = (2*close - high - low) / (high - low) * volume`
- 做 20 周期 SMA 平滑

### Volume Weighted RSI(14)

方法：

- 上涨幅度按 volume 加权，下跌幅度按 volume 加权
- 再按标准 RSI 公式计算

### Relative Volume(5)

方法：

- `RV5 = volume / SMA(volume, 5)`

### Tick Intensity

方法：

- `Tick Intensity = abs(close - open) / (high - low)`
- 即实体绝对值占全K线范围的比例

### Amihud Illiquidity(20)

方法：

- `Amihud = mean(abs(return) / volume, 20)`
- 值越大表示流动性越差

### Kyle Lambda(20)

方法：

- 对最近 20 根 `abs(return)` 和 `volume` 做线性回归
- `Kyle Lambda = 回归斜率`
- 反映单位成交量对价格的影响程度

### Return Dispersion(20)

方法：

- `Return Dispersion = std(return_1, 20) / abs(mean(return_1, 20))`
- 即变异系数，反映收益率的离散程度

### Overnight Gap %

方法：

- `Gap = (open - prev_close) / prev_close * 100`
- 反映相邻K线间的跳空幅度

## 时间对齐方法

技术指标和市场上下文的对齐方式如下：

- 先计算每根 K 线的 `candle_close_time = open_time + timeframe`
- 对每个交易所的 `ticker / funding / orderbook` 数据分别做 `asof backward merge`
- 取不晚于 `candle_close_time` 的最近一条快照
- 再对多个交易所做横向聚合，生成同一根K线的一组上下文特征

这样做比“直接拿最新一条快照覆盖所有历史K线”更合理，至少保证了时间方向不穿越未来。

当前实现细节：

- 先计算 `candle_close_time`
- 对每个交易所分别做 `merge_asof(direction="backward")`
- 但不会无限向后拖尾旧快照，而是按真实采集频率施加 freshness 容忍窗口
  - `ticker` 只允许使用最近 `max(15s, ticker_interval*3)` 的快照
  - `orderbook` 只允许使用最近 `max(15s, orderbook_interval*3)` 的快照
  - `funding` 只允许使用最近 `max(60s, funding_interval*3)` 的快照
- 超过 freshness 窗口的旧快照会直接被剥离为空值，而不是继续伪装成当前市场上下文
- 对同一时刻多交易所快照做横向均值、求和、标准差和范围聚合
- 没有可用快照时保留空值，不伪造样本
- 增量刷新时，只读取当前计算窗口内的快照，并额外补每个交易所在 cutoff 前最后一条锚点样本，避免为时间对齐去扫描整张高频历史表

这样做的原因是：

- `merge_asof` 只能保证时间方向不穿越未来，但不能自动保证“足够新”
- 如果不加 freshness 限制，历史上最后一条 `ticker / funding / orderbook` 可能被一路拖到很多根后续 K 线
- 这会让 `technical_indicators` 看起来“上下文有值”，但其实给 AI 的是过期市场状态
- 当前项目的目标是给 AI 喂真实市场世界，而不是用旧快照把缺口涂平

## 增量计算策略

默认模式已经改成增量刷新，不再每次全量重算。

### merge 增量

- 对 `merged_klines`，默认从该 `symbol + timeframe` 上次已合并的最后一根 K 线开始重拉并 UPSERT

### indicators 增量

- 对 `technical_indicators`，默认只回看最近 `200` 根 K 线窗口后重算
- 这样可以覆盖当前所有长窗口指标，例如 `SMA120`、`Ichimoku52`、`ADX14`
- 保存时用 UPSERT 覆盖这一段窗口，避免整表重算

为什么用 `200` 根：

- 需要覆盖长周期均线
- 需要覆盖 `Ichimoku 52`
- 需要给 `ADX / ATR / MFI / CCI / KAMA / Supertrend / KST / RVI / Mass Index` 等滚动窗口留下足够热身长度

如果你要强制全量重算，可以使用：

```bash
python -m logic_layer.technical_indicators.runner --mode all --full-refresh
```

## 数据库表

- `merged_klines`
  - 合并后的统一主K线
- `technical_indicators`
  - 指标计算结果与市场上下文特征

## 当前质量语义

这里要特别注意：

- `technical_indicators` 的上下文列现在只代表“在 freshness 窗口内仍可成立的 ticker/funding/orderbook 语境”
- 这里的空值不一定表示从来没采到过，而可能表示“确实采到过，但已经过期，不再适合直接给 AI 用”
- 这和 `exchange_data` 主 bundle 的质量治理口径保持一致，避免一个模块说旧、另一个模块却继续把同一批旧快照当成可用上下文

### 新增的上下文质量字段

为了避免下游只能靠空值猜测原因，当前 `technical_indicators` 已额外写出每行的上下文质量摘要：

- `ticker_context_status / funding_context_status / orderbook_context_status`
  - 取值为 `ready / partial / stale_only / missing`
- `*_context_known_exchange_count`
  - 当前该 symbol 在对应上下文里一共识别到了多少真实交易所来源
- `*_context_raw_exchange_count`
  - 当前 K 线时点之前，实际能对齐到多少交易所的历史快照，不论是否已过 freshness
- `*_context_fresh_exchange_count`
  - 其中仍在 freshness 窗口内、还能直接给 AI 用的交易所数量
- `*_context_stale_exchange_count`
  - 虽然存在历史快照，但已经过期而被剥离的交易所数量
- `*_context_missing_exchange_count`
  - 当前时点之前根本没有对齐到任何历史快照的交易所数量
- `*_context_fresh_exchange_ratio`
  - `fresh_exchange_count / known_exchange_count`

同时还会输出整行级别的聚合质量字段：

- `market_context_quality_flag`
  - 当前取值为 `ok / partial / thin`
- `market_context_quality_flags`
  - 例如 `ticker_context_partial|funding_context_missing|orderbook_context_stale_only`
- `market_context_ready_source_count`
- `market_context_partial_source_count`
- `market_context_stale_only_source_count`
- `market_context_missing_source_count`

这些字段的目的不是给策略打分，而是明确告诉后续模块：

- 当前这根 K 线的市场上下文为什么完整或不完整
- 是完全没采到
- 还是确实采到了，但只有 stale 历史快照，因此已被主动剥离

## 运行方式

合并并计算全部指标：

```bash
python -m logic_layer.technical_indicators.runner --mode all
```

只处理某个币种和周期：

```bash
python -m logic_layer.technical_indicators.runner --mode all --symbol BTC/USDT --timeframe 1h
```

只处理最近 7 天：

```bash
python -m logic_layer.technical_indicators.runner --mode all --since-days 7
```

强制全量重算：

```bash
python -m logic_layer.technical_indicators.runner --mode all --full-refresh
```

增量模式说明：

- 不加 `--full-refresh` 时，默认走增量模式
- 新增 K 线只会触发最近窗口重算
- 这更适合长期运行，不会随着数据量增长而线性变慢

## 当前限制

- 如果数据层中 `ticker / funding / orderbook` 样本还不够，很多上下文字段会是空值，这属于预期行为。
- `orderbook` 在当前库里如果采样很少，只会覆盖少数币种和时刻。
- `Ichimoku` 当前保存的是未前移版本，便于当前时点消费，但和部分图表软件显示方式会略有差异。
- 长窗口和复合指标越多，对历史 K 线长度要求越高；数据不足时空值是正常现象。

## 后续扩展

### Phase 2

- 增加多交易所价差、基差、相对强弱等横截面特征
- 将清算数据、未平仓量、长短仓比继续并入特征表

### Phase 3

- 按策略分层建立 `trend_features`、`mean_reversion_features`、`microstructure_features`
- 增加在线增量计算，避免每次全量回算
- 增加异常值过滤和缺失补数
