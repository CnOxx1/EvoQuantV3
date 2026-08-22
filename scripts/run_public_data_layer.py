"""Run only EvoQuant's free public raw-data collectors; never invoke logic_layer."""

from __future__ import annotations

import subprocess
import sys


COLLECTORS = (
    "data_layer.exchange_data.runner",
    "data_layer.macro_data.runner",
    "data_layer.news_data.runner",
    "data_layer.onchain_data.runner",
    "data_layer.options_data.runner",
    "data_layer.defi_protocol_data.runner",
    "data_layer.governance_data.runner",
    "data_layer.gas_network_data.runner",
    "data_layer.mempool_data.runner",
    "data_layer.mev_data.runner",
    "data_layer.miner_data.runner",
    "data_layer.stablecoin_flow_data.runner",
    "data_layer.onchain_address_data.runner",
    "data_layer.exchange_reserve_data.runner",
)


def main() -> int:
    failed = []
    for module in COLLECTORS:
        result = subprocess.run([sys.executable, "-m", module, "--mode", "once"], check=False)
        if result.returncode:
            failed.append(module)
    print({"collectors": len(COLLECTORS), "failed": failed})
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
