#!/usr/bin/env python3
"""Persist paper world-model objects (B,U,H,S,C,WMI,ACWMI,tilts) into analytics DB.

Paper empirics compute S/C from return engines in ``run_pit_jf_experiments``.
Production AI bundles may otherwise fall back to readiness proxies. Writing
daily rows into ``paper_world_model_snapshots`` makes the paper objects
queryable via ``/time-slice/paper-world-model`` and lets live bundles attach
``acwmi_input_source=paper_engines`` when engines have been run.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]


PAPER_COLS = [
    "date",
    "asset",
    "symbol",
    "B_hier",
    "U",
    "H_cont",
    "S",
    "C",
    "C_base",
    "WMI",
    "ACWMI",
    "macro_tilt",
    "alt_tilt",
    "signal",
    "detected_regime",
    "mom5",
    "cascade_p",
    "scarce",
    "outage",
    "vix_chg5",
    "dxy_chg5",
]


def _ensure_table(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS paper_world_model_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            decision_date TEXT NOT NULL,
            asset TEXT NOT NULL,
            symbol TEXT,
            B_hier REAL,
            U REAL,
            H_cont REAL,
            S REAL,
            C REAL,
            C_base REAL,
            WMI REAL,
            ACWMI REAL,
            macro_tilt REAL,
            alt_tilt REAL,
            signal REAL,
            detected_regime TEXT,
            mom5 REAL,
            cascade_p REAL,
            scarce INTEGER,
            outage INTEGER,
            vix_chg5 REAL,
            dxy_chg5 REAL,
            acwmi_input_source TEXT NOT NULL DEFAULT 'paper_engines',
            content_source_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(decision_date, asset)
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_paper_wmi_date
        ON paper_world_model_snapshots(decision_date)
        """
    )


def panel_to_snapshot_rows(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Convert an attached-engine PIT panel into snapshot dicts."""
    out: list[dict[str, Any]] = []
    for _, r in df.iterrows():
        asset = str(r.get("asset") or "")
        symbol = str(r.get("symbol") or (f"{asset}/USDT" if asset else ""))
        d = pd.Timestamp(r["date"]).normalize().strftime("%Y-%m-%d")
        content = {
            "macro_tilt": float(r.get("macro_tilt") or 0.0),
            "alt_tilt": float(r.get("alt_tilt") or 0.0),
            "vix_chg5": float(r["vix_chg5"]) if pd.notna(r.get("vix_chg5")) else None,
            "dxy_chg5": float(r["dxy_chg5"]) if pd.notna(r.get("dxy_chg5")) else None,
            "source": "paper_pit_engines",
        }
        out.append(
            {
                "decision_date": d,
                "asset": asset,
                "symbol": symbol,
                "B_hier": float(r.get("B_hier") or 0.0),
                "U": float(r.get("U") or 0.0),
                "H_cont": float(r.get("H_cont") or 0.0),
                "S": float(r.get("S") or 0.0),
                "C": float(r.get("C") or 0.0),
                "C_base": float(r.get("C_base") or 0.0) if pd.notna(r.get("C_base")) else None,
                "WMI": float(r.get("WMI") or 0.0),
                "ACWMI": float(r.get("ACWMI") or 0.0),
                "macro_tilt": float(r.get("macro_tilt") or 0.0),
                "alt_tilt": float(r.get("alt_tilt") or 0.0),
                "signal": float(r.get("signal") or 0.0),
                "detected_regime": str(r.get("detected_regime") or ""),
                "mom5": float(r.get("mom5") or 0.0) if pd.notna(r.get("mom5")) else None,
                "cascade_p": float(r.get("cascade_p") or 0.0) if pd.notna(r.get("cascade_p")) else None,
                "scarce": int(r.get("scarce") or 0) if pd.notna(r.get("scarce")) else 0,
                "outage": int(r.get("outage") or 0) if pd.notna(r.get("outage")) else 0,
                "vix_chg5": float(r["vix_chg5"]) if pd.notna(r.get("vix_chg5")) else None,
                "dxy_chg5": float(r["dxy_chg5"]) if pd.notna(r.get("dxy_chg5")) else None,
                "acwmi_input_source": "paper_engines",
                "content_source_json": json.dumps(content, ensure_ascii=False),
            }
        )
    return out


def persist_paper_world_model(
    df: pd.DataFrame,
    *,
    db_path: Path | None = None,
    replace: bool = True,
) -> int:
    """Write paper objects into analytics SQLite. Returns rows written."""
    import sqlite3

    path = db_path or (ROOT / "database" / "analytics.db")
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = panel_to_snapshot_rows(df)
    if not rows:
        return 0
    con = sqlite3.connect(str(path))
    try:
        _ensure_table(con)
        if replace:
            con.execute("DELETE FROM paper_world_model_snapshots")
        con.executemany(
            """
            INSERT OR REPLACE INTO paper_world_model_snapshots (
                decision_date, asset, symbol, B_hier, U, H_cont, S, C, C_base,
                WMI, ACWMI, macro_tilt, alt_tilt, signal, detected_regime,
                mom5, cascade_p, scarce, outage, vix_chg5, dxy_chg5,
                acwmi_input_source, content_source_json
            ) VALUES (
                :decision_date, :asset, :symbol, :B_hier, :U, :H_cont, :S, :C, :C_base,
                :WMI, :ACWMI, :macro_tilt, :alt_tilt, :signal, :detected_regime,
                :mom5, :cascade_p, :scarce, :outage, :vix_chg5, :dxy_chg5,
                :acwmi_input_source, :content_source_json
            )
            """,
            rows,
        )
        con.commit()
    finally:
        con.close()
    return len(rows)


def load_paper_world_model(
    *,
    date: str | None = None,
    asset: str | None = None,
    symbol: str | None = None,
    limit: int = 500,
    db_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Query persisted paper objects (used by API and tests)."""
    import sqlite3

    path = db_path or (ROOT / "database" / "analytics.db")
    if not path.exists():
        return []
    con = sqlite3.connect(str(path))
    con.row_factory = sqlite3.Row
    try:
        exists = con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='paper_world_model_snapshots'"
        ).fetchone()
        if not exists:
            return []
        clauses: list[str] = []
        params: list[Any] = []
        if date:
            clauses.append("decision_date = ?")
            params.append(date[:10])
        if asset:
            clauses.append("asset = ?")
            params.append(asset)
        if symbol:
            clauses.append("symbol = ?")
            params.append(symbol)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(int(limit))
        cur = con.execute(
            f"""
            SELECT decision_date, asset, symbol, B_hier, U, H_cont, S, C, C_base,
                   WMI, ACWMI, macro_tilt, alt_tilt, signal, detected_regime,
                   mom5, cascade_p, scarce, outage, vix_chg5, dxy_chg5,
                   acwmi_input_source, content_source_json
            FROM paper_world_model_snapshots
            {where}
            ORDER BY decision_date DESC, asset
            LIMIT ?
            """,
            params,
        )
        out = []
        for row in cur.fetchall():
            rec = dict(row)
            raw = rec.pop("content_source_json", None)
            if raw:
                try:
                    rec["content_provenance"] = json.loads(raw)
                except json.JSONDecodeError:
                    rec["content_provenance"] = {}
            else:
                rec["content_provenance"] = {}
            out.append(rec)
        return out
    finally:
        con.close()
