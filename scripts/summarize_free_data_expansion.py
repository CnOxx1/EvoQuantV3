"""Summarize verified free-data expansion tables."""
from __future__ import annotations
import json, sqlite3
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
TABLES={"exchange_data.db":["okx_derivatives_raw","public_exchange_quote_snapshots","funding_rates","open_interest_snapshots","liquidation_bars","basis_snapshots"],"market_data.db":["asset_metadata_snapshots","asset_exchange_pair_mappings","asset_project_categories","bitcoin_onchain_history","stablecoin_chain_flows"]}
def main():
    out={}
    for db_name,tables in TABLES.items():
        conn=sqlite3.connect(ROOT/"database"/db_name); data={}
        for table in tables:
            exists=conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone()
            data[table]=int(conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]) if exists else None
        conn.close(); out[db_name]=data
    path=ROOT/"reports"/"free_data_expansion_summary.json"; path.parent.mkdir(exist_ok=True); path.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8"); print(json.dumps(out,ensure_ascii=False,indent=2))
if __name__=="__main__": main()
