from __future__ import annotations

import csv
import io
import sqlite3
import unittest
import zipfile
from types import SimpleNamespace

from data_layer.exchange_reserve_data.client import ExchangeReserveDataClient
from data_layer.exchange_reserve_data.service import ExchangeReserveDataService


class _Response:
    def __init__(self, text: str = "", content: bytes = b""):
        self.text = text
        self.content = content

    def raise_for_status(self) -> None:
        return None


class _Http:
    def __init__(self, page: str, archive: bytes):
        self.page = page
        self.archive = archive

    def get(self, url: str, **_kwargs) -> _Response:
        return _Response(text=self.page) if url.endswith("/download") else _Response(content=self.archive)

    def close(self) -> None:
        return None


class _ReserveClient:
    def fetch_okx_reserves(self) -> dict:
        return {
            "exchange": "OKX", "report_at": "2026-07-07T00:00:00+00:00",
            "archive_url": "https://static.okx.com/report.zip",
            "source_kind": "okx_official_proof_of_reserves",
            "assets": [{"asset": "BTC", "reserve_balance": 10.5}],
        }

    def close(self) -> None:
        return None


def _archive() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        with archive.open("okx_por_2026070700_V3.csv", "w") as binary:
            text = io.TextIOWrapper(binary, encoding="utf-8", newline="")
            writer = csv.writer(text)
            writer.writerow(["coin", "amount"])
            writer.writerow(["BTC", "1.5"])
            writer.writerow(["BTC", "2.5"])
            text.flush()
    return buffer.getvalue()


class TestOkxProofOfReserves(unittest.TestCase):
    def test_client_discovers_and_aggregates_official_csv(self) -> None:
        client = ExchangeReserveDataClient()
        client._http = _Http(
            '<a href="https://static.okx.com/cdn/okx/por/chain/por_csv_2026070700_V3.zip">x</a>',
            _archive(),
        )
        report = client.fetch_okx_reserves()
        self.assertEqual(report["report_at"], "2026-07-07T00:00:00+00:00")
        self.assertEqual(report["assets"], [{"asset": "BTC", "reserve_balance": 4.0}])

    def test_service_persists_source_backed_snapshot(self) -> None:
        connection = sqlite3.connect(":memory:")
        service = ExchangeReserveDataService(client=_ReserveClient(), db=SimpleNamespace(conn=connection))
        service.init_storage()
        service.collect_once()
        row = connection.execute(
            "SELECT exchange, asset, reserve_balance, source_kind FROM exchange_reserves"
        ).fetchone()
        self.assertEqual(row, ("OKX", "BTC", 10.5, "okx_official_proof_of_reserves"))


if __name__ == "__main__":
    unittest.main()
