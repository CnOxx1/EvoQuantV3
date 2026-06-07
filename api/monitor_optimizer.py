from __future__ import annotations

from loguru import logger


class MonitorBatchFetcher:
    """Batch query optimizer for monitor endpoints - replaces per-symbol loops."""

    def fetch_tickers_batch(self, db, symbols: list[str]) -> dict[str, dict]:
        if not symbols:
            return {}
        placeholders = ",".join(["%s"] * len(symbols))
        query = f"SELECT * FROM tickers WHERE symbol IN ({placeholders}) ORDER BY timestamp DESC"
        rows = db.execute(query, symbols).fetchall()
        result: dict[str, dict] = {}
        for row in rows:
            sym = row["symbol"]
            if sym not in result:
                result[sym] = dict(row)
        logger.debug(f"Batch fetched tickers for {len(result)}/{len(symbols)} symbols")
        return result

    def fetch_funding_batch(self, db, symbols: list[str]) -> dict[str, dict]:
        if not symbols:
            return {}
        placeholders = ",".join(["%s"] * len(symbols))
        query = f"SELECT * FROM funding_rates WHERE symbol IN ({placeholders}) ORDER BY timestamp DESC"
        rows = db.execute(query, symbols).fetchall()
        result: dict[str, dict] = {}
        for row in rows:
            sym = row["symbol"]
            if sym not in result:
                result[sym] = dict(row)
        logger.debug(f"Batch fetched funding for {len(result)}/{len(symbols)} symbols")
        return result

    def fetch_oi_batch(self, db, symbols: list[str]) -> dict[str, dict]:
        if not symbols:
            return {}
        placeholders = ",".join(["%s"] * len(symbols))
        query = f"SELECT * FROM open_interest WHERE symbol IN ({placeholders}) ORDER BY timestamp DESC"
        rows = db.execute(query, symbols).fetchall()
        result: dict[str, dict] = {}
        for row in rows:
            sym = row["symbol"]
            if sym not in result:
                result[sym] = dict(row)
        logger.debug(f"Batch fetched OI for {len(result)}/{len(symbols)} symbols")
        return result

    def fetch_all_monitor_data(self, db, symbols: list[str]) -> dict[str, dict]:
        tickers = self.fetch_tickers_batch(db, symbols)
        funding = self.fetch_funding_batch(db, symbols)
        oi = self.fetch_oi_batch(db, symbols)
        combined: dict[str, dict] = {}
        for sym in symbols:
            combined[sym] = {
                "ticker": tickers.get(sym, {}),
                "funding": funding.get(sym, {}),
                "oi": oi.get(sym, {}),
            }
        return combined


monitor_batch = MonitorBatchFetcher()
