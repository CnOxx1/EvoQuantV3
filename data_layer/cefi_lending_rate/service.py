"""cefi_lending_rate 服务层。"""

from datetime import datetime, timezone

from loguru import logger

from data_layer.cefi_lending_rate.client import CefiLendingRateClient

from config.symbols import TARGET_ASSET_CODES

TARGET_ASSETS = TARGET_ASSET_CODES


class CefiLendingRateService:
    """CeFi 借贷利率数据采集与价差分析服务。"""

    def __init__(self, client=None, db=None):
        if db is not None:
            self.db = db
        else:
            from database.router import DatabaseRouter, Domain
            self.db = DatabaseRouter().get_manager(Domain.MARKET_DATA)
        self.client = client or CefiLendingRateClient()

    def init_storage(self):
        """初始化数据库表。"""
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS cefi_lending_rates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                platform TEXT NOT NULL,
                asset TEXT NOT NULL,
                product_type TEXT NOT NULL,
                supply_apy REAL DEFAULT 0,
                borrow_apy REAL DEFAULT 0,
                utilization_pct REAL DEFAULT 0,
                min_amount REAL DEFAULT 0,
                collected_at TEXT NOT NULL,
                UNIQUE(ts, platform, asset, product_type)
            )
        """)
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS lending_rate_spread (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                asset TEXT NOT NULL,
                cefi_avg_supply REAL DEFAULT 0,
                defi_avg_supply REAL DEFAULT 0,
                cefi_avg_borrow REAL DEFAULT 0,
                defi_avg_borrow REAL DEFAULT 0,
                supply_spread REAL DEFAULT 0,
                borrow_spread REAL DEFAULT 0,
                spread_signal TEXT DEFAULT '',
                collected_at TEXT NOT NULL,
                UNIQUE(ts, asset)
            )
        """)
        self.db.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_cefi_lending_rates_ts
            ON cefi_lending_rates(ts DESC)
        """)
        self.db.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_lending_rate_spread_ts
            ON lending_rate_spread(ts DESC)
        """)
        self.db.conn.commit()
        logger.info("cefi_lending_rate 存储初始化完成")

    def bootstrap(self, assets: list[str] | None = None):
        """首次回填。"""
        assets = assets or TARGET_ASSETS
        logger.info(f"开始 bootstrap，目标资产: {assets}")
        self._collect_binance(assets)
        self._collect_okx(assets)
        self._collect_bybit(assets)
        self._compute_spreads(assets)
        logger.info("bootstrap 完成")

    def collect_once(self, assets: list[str] | None = None):
        """执行一次采集周期。"""
        assets = assets or TARGET_ASSETS
        self._collect_binance(assets)
        self._collect_okx(assets)
        self._collect_bybit(assets)
        self._compute_spreads(assets)
        logger.info("collect_once 完成")

    def _collect_binance(self, assets: list[str]):
        """采集 Binance 借贷利率。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        for asset in assets:
            rows = self.client.fetch_binance_lending_rates(asset)
            for row in rows:
                supply_apy = float(row.get("latestAnnualPercentageRate", 0) or 0) * 100
                min_amt = float(row.get("minPurchaseAmount", 0) or 0)
                self.db.conn.execute("""
                    INSERT OR REPLACE INTO cefi_lending_rates
                    (ts, platform, asset, product_type, supply_apy, borrow_apy,
                     utilization_pct, min_amount, collected_at)
                    VALUES (?, 'binance', ?, 'flexible', ?, 0, 0, ?, ?)
                """, (now_iso, asset, supply_apy, min_amt, now_iso))

            margin = self.client.fetch_binance_margin_rates(asset)
            if margin:
                borrow_rate = float(margin.get("nextHourlyInterestRate", 0) or 0)
                borrow_apy = borrow_rate * 24 * 365 * 100
                self.db.conn.execute("""
                    INSERT OR REPLACE INTO cefi_lending_rates
                    (ts, platform, asset, product_type, supply_apy, borrow_apy,
                     utilization_pct, min_amount, collected_at)
                    VALUES (?, 'binance', ?, 'margin', 0, ?, 0, 0, ?)
                """, (now_iso, asset, borrow_apy, now_iso))
        self.db.conn.commit()

    def _collect_okx(self, assets: list[str]):
        """采集 OKX 借贷利率。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        rows = self.client.fetch_okx_lending_rates()
        for row in rows:
            ccy = row.get("ccy", "")
            if ccy not in assets:
                continue
            rate = float(row.get("rate", 0) or 0)
            supply_apy = rate * 365 * 100
            self.db.conn.execute("""
                INSERT OR REPLACE INTO cefi_lending_rates
                (ts, platform, asset, product_type, supply_apy, borrow_apy,
                 utilization_pct, min_amount, collected_at)
                VALUES (?, 'okx', ?, 'lending', ?, 0, 0, 0, ?)
            """, (now_iso, ccy, supply_apy, now_iso))
        self.db.conn.commit()

    def _collect_bybit(self, assets: list[str]):
        """采集 Bybit 借贷利率。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        rows = self.client.fetch_bybit_lending_rates()
        for row in rows:
            coin = row.get("coin", "")
            if coin not in assets:
                continue
            supply_apy = float(row.get("annualYieldRate", 0) or 0) * 100
            min_amt = float(row.get("minAmount", 0) or 0)
            self.db.conn.execute("""
                INSERT OR REPLACE INTO cefi_lending_rates
                (ts, platform, asset, product_type, supply_apy, borrow_apy,
                 utilization_pct, min_amount, collected_at)
                VALUES (?, 'bybit', ?, 'earn', ?, 0, 0, ?, ?)
            """, (now_iso, coin, supply_apy, min_amt, now_iso))
        self.db.conn.commit()

    def _compute_spreads(self, assets: list[str]):
        """计算 CeFi vs DeFi 利率价差。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

        for asset in assets:
            # CeFi 平均供给利率
            cursor = self.db.conn.execute("""
                SELECT AVG(supply_apy), AVG(borrow_apy)
                FROM cefi_lending_rates
                WHERE asset = ? AND ts >= datetime('now', '-2 hours')
                  AND supply_apy > 0
            """, (asset,))
            cefi_row = cursor.fetchone()
            cefi_avg_supply = cefi_row[0] if cefi_row and cefi_row[0] else 0.0
            cefi_avg_borrow = cefi_row[1] if cefi_row and cefi_row[1] else 0.0

            # DeFi 利率（从 defi_protocol_data 表获取，若不存在则默认 0）
            defi_avg_supply = 0.0
            defi_avg_borrow = 0.0
            try:
                cursor = self.db.conn.execute("""
                    SELECT AVG(supply_apy), AVG(borrow_apy)
                    FROM defi_lending_rates
                    WHERE asset = ? AND ts >= datetime('now', '-2 hours')
                """, (asset,))
                defi_row = cursor.fetchone()
                if defi_row and defi_row[0]:
                    defi_avg_supply = defi_row[0]
                if defi_row and defi_row[1]:
                    defi_avg_borrow = defi_row[1]
            except Exception:
                pass  # defi_lending_rates 表可能不存在

            supply_spread = cefi_avg_supply - defi_avg_supply
            borrow_spread = cefi_avg_borrow - defi_avg_borrow

            # 信号判定
            if defi_avg_supply > cefi_avg_supply and defi_avg_supply > 0:
                spread_signal = "defi_premium_deleverage"
            elif supply_spread > 2.0:
                spread_signal = "cefi_premium_high"
            elif supply_spread < -2.0:
                spread_signal = "defi_premium_high"
            else:
                spread_signal = "neutral"

            self.db.conn.execute("""
                INSERT OR REPLACE INTO lending_rate_spread
                (ts, asset, cefi_avg_supply, defi_avg_supply, cefi_avg_borrow,
                 defi_avg_borrow, supply_spread, borrow_spread, spread_signal,
                 collected_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (now_iso, asset, round(cefi_avg_supply, 4),
                  round(defi_avg_supply, 4), round(cefi_avg_borrow, 4),
                  round(defi_avg_borrow, 4), round(supply_spread, 4),
                  round(borrow_spread, 4), spread_signal, now_iso))
        self.db.conn.commit()

    def load_latest_context_bundle(self, assets: list[str] | None = None) -> dict:
        """输出 AI 可读的 CeFi 借贷利率上下文 bundle。

        包含：
        - CeFi vs DeFi 利率价差
        - 利率倒挂检测（DeFi > CeFi = 去杠杆信号）
        - 各平台利率排名
        - 利率趋势（上升/下降/稳定）
        """
        assets = assets or TARGET_ASSETS
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

        # 各平台最新利率
        placeholders = ",".join("?" * len(assets))
        cursor = self.db.conn.execute(f"""
            SELECT platform, asset, product_type, supply_apy, borrow_apy
            FROM cefi_lending_rates
            WHERE asset IN ({placeholders})
              AND ts >= datetime('now', '-2 hours')
            ORDER BY supply_apy DESC
        """, tuple(assets))
        rate_rows = cursor.fetchall()

        # 价差数据
        cursor = self.db.conn.execute(f"""
            SELECT asset, cefi_avg_supply, defi_avg_supply, cefi_avg_borrow,
                   defi_avg_borrow, supply_spread, borrow_spread, spread_signal
            FROM lending_rate_spread
            WHERE asset IN ({placeholders})
            ORDER BY ts DESC
        """, tuple(assets))
        spread_rows = cursor.fetchall()

        if not rate_rows and not spread_rows:
            return {"status": "no_data", "as_of": now_iso}

        # 各平台利率排名
        platform_rates = {}
        for row in rate_rows:
            platform, asset, product_type, supply_apy, borrow_apy = row
            key = f"{platform}_{asset}"
            if key not in platform_rates:
                platform_rates[key] = {
                    "platform": platform,
                    "asset": asset,
                    "product_type": product_type,
                    "supply_apy": round(supply_apy, 4),
                    "borrow_apy": round(borrow_apy, 4),
                }

        # 价差摘要与倒挂检测
        spreads = {}
        deleverage_signals = []
        seen_assets = set()
        for row in spread_rows:
            asset = row[0]
            if asset in seen_assets:
                continue
            seen_assets.add(asset)
            signal = row[7]
            spreads[asset] = {
                "cefi_avg_supply": round(row[1], 4),
                "defi_avg_supply": round(row[2], 4),
                "cefi_avg_borrow": round(row[3], 4),
                "defi_avg_borrow": round(row[4], 4),
                "supply_spread": round(row[5], 4),
                "borrow_spread": round(row[6], 4),
                "signal": signal,
            }
            if signal == "defi_premium_deleverage":
                deleverage_signals.append(asset)

        # 利率趋势（对比 6 小时前）
        rate_trends = {}
        for asset in assets:
            cursor = self.db.conn.execute("""
                SELECT AVG(supply_apy) FROM cefi_lending_rates
                WHERE asset = ? AND ts >= datetime('now', '-2 hours')
            """, (asset,))
            current = cursor.fetchone()
            cursor = self.db.conn.execute("""
                SELECT AVG(supply_apy) FROM cefi_lending_rates
                WHERE asset = ? AND ts >= datetime('now', '-8 hours')
                  AND ts < datetime('now', '-2 hours')
            """, (asset,))
            previous = cursor.fetchone()
            curr_val = current[0] if current and current[0] else 0
            prev_val = previous[0] if previous and previous[0] else 0
            if prev_val == 0:
                rate_trends[asset] = "insufficient_data"
            elif curr_val > prev_val * 1.1:
                rate_trends[asset] = "rising"
            elif curr_val < prev_val * 0.9:
                rate_trends[asset] = "falling"
            else:
                rate_trends[asset] = "stable"

        return {
            "status": "ready",
            "as_of": now_iso,
            "window": "2h",
            "market_signal": {
                "deleverage_detected": deleverage_signals,
                "rate_inversion_count": len(deleverage_signals),
                "interpretation": (
                    "DeFi利率高于CeFi，去杠杆信号"
                    if deleverage_signals else "利率结构正常"
                ),
            },
            "platform_rates": platform_rates,
            "cefi_defi_spreads": spreads,
            "rate_trends": rate_trends,
            "coverage": {
                "assets_tracked": len(assets),
                "platforms": ["binance", "okx", "bybit"],
                "rate_records": len(rate_rows),
            },
        }

    def build_scheduler(self, assets: list[str] | None = None):
        """构建阻塞式定时调度器，每 60 分钟采集一次。"""
        from apscheduler.schedulers.blocking import BlockingScheduler
        scheduler = BlockingScheduler()
        scheduler.add_job(
            self.collect_once, "interval", minutes=60,
            kwargs={"assets": assets}, id="cefi_lending_rate_collect",
        )
        return scheduler

    def build_async_scheduler(self, assets: list[str] | None = None):
        """构建异步定时调度器，每 60 分钟采集一次。"""
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        scheduler = AsyncIOScheduler()
        scheduler.add_job(
            self.collect_once, "interval", minutes=60,
            kwargs={"assets": assets}, id="cefi_lending_rate_collect",
        )
        return scheduler

    def close(self):
        """关闭客户端连接。"""
        self.client.close()
