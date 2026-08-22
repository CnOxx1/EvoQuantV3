"""gas_network_data HTTP 客户端。"""

import os

import httpx
from loguru import logger


class GasNetworkClient:
    """Gas 与网络拥堵数据 API 客户端。

    数据源：
    - Etherscan API (Gas Oracle, Fee History, Pending Tx)
    - Blocknative API (Gas Prices, Mempool Stats)
    """

    BASE_URLS = {
        "etherscan": "https://api.etherscan.io/api",
        "blocknative": "https://api.blocknative.com",
        "metaswap_gas": "https://gas-api.metaswap.codefi.network/networks/1/suggestedGasFees",
        "blockchair_eth": "https://api.blockchair.com/ethereum/stats",
    }

    def __init__(self, etherscan_key: str = "", blocknative_key: str = ""):
        self.etherscan_key = etherscan_key or os.environ.get("ETHERSCAN_API_KEY", "")
        self.blocknative_key = blocknative_key or os.environ.get("BLOCKNATIVE_API_KEY", "")
        self._http = httpx.Client(timeout=30, follow_redirects=True)

    def fetch_etherscan_gas_oracle(self) -> dict:
        """从 Etherscan 获取当前 Gas Oracle 数据。"""
        try:
            resp = self._http.get(
                self.BASE_URLS["etherscan"],
                params={
                    "module": "gastracker",
                    "action": "gasoracle",
                    "apikey": self.etherscan_key,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("result", {})
        except Exception as e:
            logger.warning(f"Etherscan Gas Oracle 请求失败: {e}")
            return {}

    def fetch_etherscan_gas_history(self, startblock: int, endblock: int) -> list[dict]:
        """从 Etherscan 获取历史 Gas 费用数据（eth_feeHistory）。"""
        try:
            resp = self._http.get(
                self.BASE_URLS["etherscan"],
                params={
                    "module": "proxy",
                    "action": "eth_feeHistory",
                    "startblock": startblock,
                    "endblock": endblock,
                    "apikey": self.etherscan_key,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            result = data.get("result", {})
            if isinstance(result, dict):
                # eth_feeHistory 返回 baseFeePerGas 列表
                base_fees = result.get("baseFeePerGas", [])
                gas_used_ratios = result.get("gasUsedRatio", [])
                return [
                    {"baseFeePerGas": fee, "gasUsedRatio": ratio}
                    for fee, ratio in zip(base_fees, gas_used_ratios)
                ]
            return []
        except Exception as e:
            logger.warning(f"Etherscan Gas History 请求失败: {e}")
            return []

    def fetch_blocknative_gas(self) -> dict:
        """从 Blocknative 获取当前 Gas 价格预估。"""
        if not self.blocknative_key:
            logger.debug("Blocknative API key 未配置，跳过")
            return {}
        try:
            resp = self._http.get(
                f"{self.BASE_URLS['blocknative']}/gasprices/blockprices",
                headers={"Authorization": self.blocknative_key},
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning(f"Blocknative Gas 请求失败: {e}")
            return {}

    def fetch_free_gas_oracle(self) -> dict:
        """无密钥备用：MetaMask Gas API 配合 Blockchair 最新区块高度。"""
        try:
            gas_response = self._http.get(self.BASE_URLS["metaswap_gas"])
            gas_response.raise_for_status()
            gas_data = gas_response.json()
            stats_response = self._http.get(self.BASE_URLS["blockchair_eth"])
            stats_response.raise_for_status()
            block_number = int((stats_response.json().get("data") or {}).get("blocks") or 0)
            medium = gas_data.get("medium") or {}
            base_fee = float(gas_data.get("estimatedBaseFee") or 0)
            priority_fee = float(medium.get("suggestedMaxPriorityFeePerGas") or 0)
            if block_number <= 0 or base_fee <= 0:
                return {}
            return {
                "suggestBaseFee": str(base_fee),
                "FastGasPrice": str(base_fee + priority_fee),
                "gasUsedRatio": "0",
                "LastBlock": str(block_number),
            }
        except Exception as exc:
            logger.warning(f"免费 Gas 备用源请求失败: {exc}")
            return {}

    def fetch_blocknative_mempool_stats(self) -> dict:
        """从 Blocknative 获取 Mempool 统计数据。"""
        if not self.blocknative_key:
            logger.debug("Blocknative API key 未配置，跳过")
            return {}
        try:
            resp = self._http.get(
                f"{self.BASE_URLS['blocknative']}/mempool/stats",
                headers={"Authorization": self.blocknative_key},
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning(f"Blocknative Mempool 请求失败: {e}")
            return {}

    def fetch_pending_tx_count(self) -> int:
        """从 Etherscan 获取当前 pending 交易数量。"""
        try:
            resp = self._http.get(
                self.BASE_URLS["etherscan"],
                params={
                    "module": "proxy",
                    "action": "eth_getBlockByNumber",
                    "tag": "pending",
                    "boolean": "false",
                    "apikey": self.etherscan_key,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            result = data.get("result", {})
            if isinstance(result, dict):
                txs = result.get("transactions", [])
                return len(txs)
            return 0
        except Exception as e:
            logger.warning(f"Etherscan pending tx 请求失败: {e}")
            return 0

    def close(self):
        """关闭 HTTP 客户端。"""
        self._http.close()
