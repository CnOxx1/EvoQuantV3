"""miner_data HTTP 客户端。"""

import httpx
from loguru import logger


class MinerDataClient:
    """矿工数据 API 客户端。

    数据源：
    - mempool.space (Mining API)
    - Blockchair Bitcoin Stats（无密钥备用）
    """

    BASE_URLS = {
        "mempool": "https://mempool.space/api",
        "blockchair": "https://api.blockchair.com",
    }

    def __init__(self):
        self._http = httpx.Client(timeout=30, follow_redirects=True)

    # ─── Mining Stats ──────────────────────────────────────────────────────

    def fetch_mining_stats(self) -> dict:
        """获取当前挖矿统计数据（算力、难度、区块奖励、收入）。"""
        stats: dict = {}

        # mempool.space: 3天算力与难度
        try:
            resp = self._http.get(
                f"{self.BASE_URLS['mempool']}/v1/mining/hashrate/3d",
            )
            resp.raise_for_status()
            data = resp.json()
            stats["hashrate_3d"] = data
            hashrates = data.get("hashrates", []) if isinstance(data, dict) else []
            if hashrates:
                latest = hashrates[-1]
                stats["hashrate"] = float(latest.get("avgHashrate", 0) or 0)
                stats["difficulty"] = float(latest.get("difficulty", 0) or 0)
        except Exception as e:
            logger.warning(f"mempool hashrate/3d 请求失败: {e}")
            stats["hashrate_3d"] = {}

        # mempool.space: 当前难度调整预测（公开文档端点）
        try:
            resp = self._http.get(
                f"{self.BASE_URLS['mempool']}/v1/difficulty-adjustment",
            )
            resp.raise_for_status()
            data = resp.json()
            stats["difficulty_adjustments"] = [data] if isinstance(data, dict) else []
        except Exception as e:
            logger.warning(f"mempool difficulty-adjustment 请求失败: {e}")
            stats["difficulty_adjustments"] = []

        # Blockchair 无密钥公开备用源。仅补足缺失的真实字段；不推造收入。
        fallback = self._fetch_blockchair_stats()
        if fallback:
            for field in ("hashrate", "difficulty", "block_reward"):
                if not stats.get(field):
                    stats[field] = fallback[field]
            stats["blockchair_snapshot"] = fallback

        return stats

    def _fetch_blockchair_stats(self) -> dict:
        """读取 Blockchair 公开统计快照，用于 Mempool 不可达时的安全降级。"""
        try:
            response = self._http.get(f"{self.BASE_URLS['blockchair']}/bitcoin/stats")
            response.raise_for_status()
            data = response.json().get("data", {})
            blocks_24h = float(data.get("blocks_24h") or 0)
            inflation_24h = float(data.get("inflation_24h") or 0)
            return {
                "hashrate": float(data.get("hashrate_24h") or 0),
                "difficulty": float(data.get("difficulty") or 0),
                # inflation_24h is satoshi; this derives the observed average
                # issuance per block without inventing a fixed subsidy.
                "block_reward": (inflation_24h / blocks_24h / 1e8) if blocks_24h > 0 else 0.0,
                "timestamp": str(data.get("best_block_time") or ""),
            }
        except Exception as exc:
            logger.warning(f"Blockchair Bitcoin stats 请求失败: {exc}")
            return {}

    # ─── Miner Outflows ───────────────────────────────────────────────────

    def fetch_miner_outflows(self) -> dict:
        """获取矿工流出数据（通过 mempool.space 矿池统计推算）。"""
        try:
            resp = self._http.get(
                f"{self.BASE_URLS['mempool']}/v1/mining/hashrate/3d",
            )
            resp.raise_for_status()
            data = resp.json()
            # 使用算力变化作为矿工压力代理指标
            return data
        except Exception as e:
            logger.warning(f"mempool miner outflows 请求失败: {e}")
            return {}

    # ─── Hashrate History ─────────────────────────────────────────────────

    def fetch_hashrate_history(self) -> list[dict]:
        """获取算力历史数据（mempool.space 3天数据）。"""
        try:
            resp = self._http.get(
                f"{self.BASE_URLS['mempool']}/v1/mining/hashrate/3d",
            )
            resp.raise_for_status()
            data = resp.json()
            hashrates = data.get("hashrates", [])
            return hashrates if isinstance(hashrates, list) else []
        except Exception as e:
            logger.warning(f"mempool hashrate history 请求失败: {e}")
            fallback = self._fetch_blockchair_stats()
            if not fallback:
                return []
            return [{
                "timestamp": fallback["timestamp"],
                "avgHashrate": fallback["hashrate"],
                "difficulty": fallback["difficulty"],
            }]

    def close(self):
        self._http.close()
