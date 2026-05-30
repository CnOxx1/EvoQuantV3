from importlib import import_module

__all__ = [
    "MultiExchangeKlineAggregator",
    "TechnicalIndicatorCalculator",
    "MarketFeatureEnricher",
    "TechnicalIndicatorRepository",
    "TechnicalIndicatorService",
]

_EXPORTS = {
    "MultiExchangeKlineAggregator": (".aggregator", "MultiExchangeKlineAggregator"),
    "TechnicalIndicatorCalculator": (".calculator", "TechnicalIndicatorCalculator"),
    "MarketFeatureEnricher": (".enricher", "MarketFeatureEnricher"),
    "TechnicalIndicatorRepository": (".repository", "TechnicalIndicatorRepository"),
    "TechnicalIndicatorService": (".service", "TechnicalIndicatorService"),
}


def __getattr__(name):
    if name not in _EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr_name = _EXPORTS[name]
    module = import_module(module_name, __name__)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value
