from __future__ import annotations

import csv
import io
import re
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

import httpx
from loguru import logger


class ExchangeReserveDataClient:
    """OKX 官方 Proof-of-Reserves CSV 客户端。

    此客户端仅处理 OKX 在公开下载页面列出的版本化储备证明文件；不使用
    DeFi TVL、未验证地址或第三方估算值替代交易所储备。
    """

    REPORTS_PAGE = "https://www.okx.com/en-us/proof-of-reserves/download"
    ARCHIVE_PATTERN = re.compile(
        r"https://static\.okx\.com/cdn/okx/por/chain/por_csv_(\d{10})_V\d+\.zip"
    )
    MAX_ARCHIVE_BYTES = 200 * 1024 * 1024

    def __init__(self):
        self._http = httpx.Client(timeout=90, follow_redirects=True)

    def discover_latest_okx_report(self) -> dict:
        """从 OKX 官方下载页发现最新可下载的储备 CSV。"""
        try:
            response = self._http.get(self.REPORTS_PAGE)
            response.raise_for_status()
            matches = self.ARCHIVE_PATTERN.findall(response.text)
            urls = self.ARCHIVE_PATTERN.finditer(response.text)
            candidates = [(match.group(1), match.group(0)) for match in urls]
            if not matches or not candidates:
                logger.warning("OKX PoR 下载页未找到可用 CSV 链接")
                return {}
            timestamp, archive_url = max(candidates, key=lambda item: item[0])
            report_at = datetime.strptime(timestamp, "%Y%m%d%H").replace(tzinfo=timezone.utc)
            return {
                "exchange": "OKX",
                "report_at": report_at.isoformat(),
                "archive_url": archive_url,
                "source_kind": "okx_official_proof_of_reserves",
            }
        except Exception as exc:
            logger.warning(f"OKX PoR 报告列表请求失败: {exc}")
            return {}

    def fetch_okx_reserves(self) -> dict:
        """下载并汇总最新版 OKX 官方 CSV 中的币种余额。"""
        report = self.discover_latest_okx_report()
        if not report:
            return {}
        try:
            response = self._http.get(report["archive_url"])
            response.raise_for_status()
            if len(response.content) > self.MAX_ARCHIVE_BYTES:
                raise ValueError("OKX PoR 归档超过安全大小限制")
            totals: dict[str, Decimal] = defaultdict(Decimal)
            archive = zipfile.ZipFile(io.BytesIO(response.content))
            for info in archive.infolist():
                if not info.filename.lower().endswith(".csv"):
                    continue
                with archive.open(info) as raw:
                    reader = csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8-sig", errors="replace"))
                    if not {"coin", "amount"}.issubset(reader.fieldnames or set()):
                        continue
                    for row in reader:
                        coin = (row.get("coin") or "").strip()
                        try:
                            amount = Decimal((row.get("amount") or "0").strip())
                        except InvalidOperation:
                            continue
                        if coin and amount >= 0:
                            totals[coin] += amount
            if not totals:
                logger.warning("OKX PoR CSV 中未解析到资产余额")
                return {}
            report["assets"] = [
                {"asset": asset, "reserve_balance": float(balance)}
                for asset, balance in sorted(totals.items())
            ]
            return report
        except Exception as exc:
            logger.warning(f"OKX PoR CSV 下载或解析失败: {exc}")
            return {}

    def close(self):
        self._http.close()
