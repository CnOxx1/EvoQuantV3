from __future__ import annotations
from collections import defaultdict, deque


class CacheDependencyGraph:
    def __init__(self) -> None:
        self._graph: dict[str, set[str]] = defaultdict(set)
        self._build_default_edges()

    def _build_default_edges(self) -> None:
        ti = "technical_indicators"
        for t in ["feature_standardization", "cross_asset_analysis",
                  "liquidation_cascade", "stablecoin_pulse", "unlock_impact",
                  "depth_regime", "smart_money_conviction", "defi_stress",
                  "onchain_lead_lag"]:
            self.add_edge(ti, t)
        self.add_edge("cross_asset_analysis", "portfolio_risk")
        self.add_edge("cross_asset_analysis", "asset_readiness")
        self.add_edge("feature_standardization", "asset_readiness")
        for src in ["portfolio_risk", "market_breadth", "asset_readiness"]:
            self.add_edge(src, "ai_market_context")
        self.add_edge("ai_market_context", "pipeline_latency")

    def add_edge(self, source: str, target: str) -> None:
        self._graph[source].add(target)

    def get_downstream(self, module_name: str) -> set[str]:
        visited: set[str] = set()
        queue = deque(self._graph.get(module_name, set()))
        while queue:
            node = queue.popleft()
            if node in visited:
                continue
            visited.add(node)
            queue.extend(self._graph.get(node, set()))
        return visited

    def get_invalidation_prefixes(self, completed_module: str) -> list[str]:
        downstream = self.get_downstream(completed_module)
        return sorted(f"{m}:" for m in downstream)


cache_deps = CacheDependencyGraph()
