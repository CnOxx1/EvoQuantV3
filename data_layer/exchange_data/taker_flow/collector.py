from data_layer.exchange_data.trades import TradesCollector


class TakerFlowCollector:
    """主动买卖流子模块。

    当前版本与 trades 共享落库表 `trade_flow_bars`，避免重复抓取同一批成交明细。
    """

    def __init__(self, trades_collector: TradesCollector):
        self.trades_collector = trades_collector

    def collect(self):
        return self.trades_collector.collect()
