from __future__ import annotations

import pytest

from api.preloader import _is_missing_table_error
from config.symbols import _resolve_csv_override


def test_csv_override_returns_default_when_environment_is_missing(monkeypatch):
    monkeypatch.delenv("EVOQUANT_TARGET_EXCHANGES", raising=False)

    result = _resolve_csv_override(
        "EVOQUANT_TARGET_EXCHANGES",
        ["binance", "okx"],
        allowed=["binance", "okx"],
    )

    assert result == ["binance", "okx"]


def test_csv_override_reads_trimmed_values(monkeypatch):
    monkeypatch.setenv("EVOQUANT_TARGET_EXCHANGES", " okx, binance ")

    result = _resolve_csv_override(
        "EVOQUANT_TARGET_EXCHANGES",
        ["binance", "okx"],
        allowed=["binance", "okx"],
    )

    assert result == ["okx", "binance"]


def test_csv_override_rejects_unknown_value(monkeypatch):
    monkeypatch.setenv("EVOQUANT_TARGET_EXCHANGES", "unknown-exchange")

    with pytest.raises(ValueError, match="EVOQUANT_TARGET_EXCHANGES"):
        _resolve_csv_override(
            "EVOQUANT_TARGET_EXCHANGES",
            ["binance", "okx"],
            allowed=["binance", "okx"],
        )


def test_missing_table_errors_are_classified_as_initialization_gaps():
    assert _is_missing_table_error(Exception("no such table: latest_tickers"))
    assert _is_missing_table_error(Exception('relation "latest_tickers" does not exist'))
    assert not _is_missing_table_error(Exception("database is locked"))
