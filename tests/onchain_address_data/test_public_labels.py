from __future__ import annotations

import sqlite3
import unittest
from types import SimpleNamespace

from data_layer.onchain_address_data.client import OnchainAddressClient
from data_layer.onchain_address_data.service import OnchainAddressService


class _Response:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {
            "entity": {"name": "Example Exchange", "category": "exchange"},
            "labels": [{"type": "exchange_cold_wallet", "sourceType": "public"}],
        }


class _Http:
    def get(self, *_args, **_kwargs) -> _Response:
        return _Response()

    def close(self) -> None:
        return None


class _LabelClient:
    def fetch_arkham_entity(self, _address: str) -> dict:
        return {}

    def fetch_public_label(self, _address: str, chain: str) -> dict:
        self.chain = chain
        return {
            "label": "exchange_cold_wallet",
            "entity": "Example Exchange",
            "category": "exchange",
            "source": "cryptolabel_public",
        }

    def fetch_arkham_whale_alerts(self, **_kwargs) -> list[dict]:
        return []

    def fetch_arkham_transfers(self, *_args, **_kwargs) -> list[dict]:
        return []

    def close(self) -> None:
        return None


class TestPublicAddressLabels(unittest.TestCase):
    def test_client_normalizes_public_label_response(self) -> None:
        client = OnchainAddressClient()
        client._http = _Http()
        label = client.fetch_public_label("0xabc")
        self.assertEqual(label["entity"], "Example Exchange")
        self.assertEqual(label["label"], "exchange_cold_wallet")
        self.assertEqual(label["source"], "cryptolabel_public")

    def test_service_stores_public_label_with_source(self) -> None:
        connection = sqlite3.connect(":memory:")
        service = OnchainAddressService(client=_LabelClient(), db=SimpleNamespace(conn=connection))
        service.TRACKED_ADDRESSES = ["0xabc"]
        service.init_storage()
        service._update_labels()
        row = connection.execute(
            "SELECT entity, category, source FROM address_labels WHERE address = ?", ("0xabc",)
        ).fetchone()
        self.assertEqual(row, ("Example Exchange", "exchange", "cryptolabel_public"))


if __name__ == "__main__":
    unittest.main()
