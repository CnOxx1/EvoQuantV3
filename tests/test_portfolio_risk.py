"""Unit tests for PortfolioRiskService."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database.db_manager import DBManager
from logic_layer.portfolio_risk.service import PortfolioRiskService


def test_init_storage_creates_tables(tmp_path):
    db = DBManager(str(tmp_path / "test.sqlite"))
    svc = PortfolioRiskService(db=db)
    svc.init_storage()

    tables = db.fetch_all(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name", ()
    )
    table_names = [row["name"] for row in tables]
    assert "portfolio_risk_snapshots" in table_names
    svc.close()


def test_load_latest_context_bundle_no_data(tmp_path):
    db = DBManager(str(tmp_path / "test.sqlite"))
    svc = PortfolioRiskService(db=db)
    svc.init_storage()

    bundle = svc.load_latest_context_bundle()
    assert "as_of" in bundle
    assert bundle["status"] == "no_data"
    svc.close()


def test_load_latest_context_bundle_with_snapshot(tmp_path):
    import json

    db = DBManager(str(tmp_path / "test.sqlite"))
    svc = PortfolioRiskService(db=db)
    svc.init_storage()

    # Insert a risk snapshot directly
    weights = {"BTC/USDT": 0.5, "ETH/USDT": 0.5}
    risk_contributions = {"BTC/USDT": 0.6, "ETH/USDT": 0.4}
    sector_concentration = {"layer1": 0.7, "defi": 0.3}
    db.conn.execute(
        """INSERT INTO portfolio_risk_snapshots
           (snapshot_time, portfolio_name, asset_count, weights_json,
            annualized_volatility, daily_var_95, daily_var_99,
            hhi, effective_n, max_weight, diversification_ratio,
            risk_contributions_json, sector_concentration_json)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        ("2025-01-01T00:00:00", "default", 2, json.dumps(weights),
         0.45, 0.029, 0.041, 0.5, 2.0, 0.5, 1.2,
         json.dumps(risk_contributions), json.dumps(sector_concentration)),
    )
    db.conn.commit()

    bundle = svc.load_latest_context_bundle()
    assert bundle["status"] == "ready"
    assert bundle["portfolio_name"] == "default"
    assert bundle["asset_count"] == 2
    assert bundle["annualized_volatility"] == 0.45
    assert bundle["hhi"] == 0.5
    assert bundle["effective_n"] == 2.0
    assert bundle["diversification_ratio"] == 1.2
    assert len(bundle["top_risk_contributors"]) == 2
    svc.close()
