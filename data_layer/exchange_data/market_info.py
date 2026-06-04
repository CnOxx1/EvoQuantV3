import json
from datetime import datetime, timezone, timedelta

from loguru import logger

from config.settings import SCHEDULER_CONFIG
from config.symbols import TARGET_SYMBOLS, TARGET_EXCHANGES
from database.db_manager import DBManager
from data_layer.exchange_data.client import ExchangeClientManager, retry_on_failure
from data_layer.exchange_data.models import MarketInfo


class MarketInfoCollector:
    """交易对静态基础信息采集器（低频，每日同步一次）"""

    def __init__(self, client_manager: ExchangeClientManager, db: DBManager):
        self.client_manager = client_manager
        self.db = db
        self._last_refresh_at: dict[str, datetime] = {}

    def _should_force_reload(self, exchange_name: str, force: bool) -> bool:
        if force:
            return True
        last_refresh = self._last_refresh_at.get(exchange_name)
        if last_refresh is None:
            return True
        ttl = timedelta(seconds=SCHEDULER_CONFIG["market_info_interval"])
        return datetime.now(timezone.utc) - last_refresh >= ttl

    @retry_on_failure
    def _load_markets(self, exchange_name: str, force: bool = False) -> dict:
        """加载交易所所有市场信息"""
        client = self.client_manager.get_client(exchange_name)
        client.load_markets(force)
        self._last_refresh_at[exchange_name] = datetime.now(timezone.utc)
        return client.markets

    def fetch_target_markets(self, force: bool = False) -> list[MarketInfo]:
        """从所有目标交易所获取目标币种的市场信息"""
        results = []

        for exchange_name in TARGET_EXCHANGES:
            try:
                markets = self._load_markets(
                    exchange_name,
                    force=self._should_force_reload(exchange_name, force),
                )
            except Exception as e:
                logger.error(f"加载市场信息失败 [{exchange_name}]: {e}")
                continue

            for symbol in TARGET_SYMBOLS:
                market = markets.get(symbol)
                if market is None:
                    logger.warning(f"交易对不存在 [{exchange_name}] {symbol}")
                    continue

                precision = market.get("precision", {})
                limits = market.get("limits", {})
                price_limits = limits.get("price", {})
                amount_limits = limits.get("amount", {})
                cost_limits = limits.get("cost", {})
                active = market.get("active")
                market_type = market.get("type")
                if not market_type:
                    if market.get("swap"):
                        market_type = "swap"
                    elif market.get("future"):
                        market_type = "future"
                    else:
                        market_type = "spot"

                info = MarketInfo(
                    symbol=symbol,
                    exchange_symbol=market.get("id") or market.get("symbol") or symbol,
                    base=market.get("base", symbol.split("/")[0]),
                    quote=market.get("quote", symbol.split("/")[1]),
                    exchange=exchange_name,
                    market_type=market_type,
                    status="active" if active is True else "suspended" if active is False else "unknown",
                    is_spot=market.get("spot"),
                    is_margin=market.get("margin"),
                    is_swap=market.get("swap"),
                    is_future=market.get("future"),
                    is_contract=market.get("contract"),
                    is_linear=market.get("linear"),
                    is_inverse=market.get("inverse"),
                    price_precision=precision.get("price"),
                    min_price=price_limits.get("min"),
                    max_price=price_limits.get("max"),
                    amount_precision=precision.get("amount"),
                    min_amount=amount_limits.get("min"),
                    max_amount=amount_limits.get("max"),
                    min_cost=cost_limits.get("min"),
                    max_cost=cost_limits.get("max"),
                    maker_fee=market.get("maker"),
                    taker_fee=market.get("taker"),
                    contract_size=market.get("contractSize"),
                    settle_currency=market.get("settle"),
                    raw_info_json=json.dumps(
                        market.get("info", {}),
                        ensure_ascii=False,
                        default=str,
                        separators=(",", ":"),
                    ),
                    updated_at=datetime.now(timezone.utc).replace(tzinfo=None),
                )
                results.append(info)
                logger.debug(f"获取市场信息: [{exchange_name}] {symbol}")

        logger.info(f"共获取 {len(results)} 条市场信息")
        return results

    def save_to_db(self, market_list: list[MarketInfo]):
        """将市场信息写入数据库（UPSERT）"""
        sql = """
            INSERT INTO market_info (
                symbol, exchange_symbol, base, quote, exchange, market_type, status,
                is_spot, is_margin, is_swap, is_future, is_contract, is_linear, is_inverse,
                price_precision, min_price, max_price,
                amount_precision, min_amount, max_amount,
                min_cost, max_cost, maker_fee, taker_fee,
                contract_size, settle_currency, raw_info_json, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol, exchange, market_type) DO UPDATE SET
                exchange_symbol=excluded.exchange_symbol,
                status=excluded.status,
                is_spot=excluded.is_spot,
                is_margin=excluded.is_margin,
                is_swap=excluded.is_swap,
                is_future=excluded.is_future,
                is_contract=excluded.is_contract,
                is_linear=excluded.is_linear,
                is_inverse=excluded.is_inverse,
                price_precision=excluded.price_precision,
                min_price=excluded.min_price,
                max_price=excluded.max_price,
                amount_precision=excluded.amount_precision,
                min_amount=excluded.min_amount,
                max_amount=excluded.max_amount,
                min_cost=excluded.min_cost,
                max_cost=excluded.max_cost,
                maker_fee=excluded.maker_fee,
                taker_fee=excluded.taker_fee,
                contract_size=excluded.contract_size,
                settle_currency=excluded.settle_currency,
                raw_info_json=excluded.raw_info_json,
                updated_at=excluded.updated_at
        """
        params_list = [
            (
                m.symbol, m.exchange_symbol, m.base, m.quote, m.exchange, m.market_type,
                m.status,
                int(m.is_spot) if m.is_spot is not None else None,
                int(m.is_margin) if m.is_margin is not None else None,
                int(m.is_swap) if m.is_swap is not None else None,
                int(m.is_future) if m.is_future is not None else None,
                int(m.is_contract) if m.is_contract is not None else None,
                int(m.is_linear) if m.is_linear is not None else None,
                int(m.is_inverse) if m.is_inverse is not None else None,
                m.price_precision, m.min_price, m.max_price,
                m.amount_precision, m.min_amount, m.max_amount,
                m.min_cost, m.max_cost, m.maker_fee, m.taker_fee,
                m.contract_size, m.settle_currency, m.raw_info_json,
                m.updated_at.isoformat(),
            )
            for m in market_list
        ]
        self.db.execute_many(sql, params_list)
        self.db.commit()
        logger.info(f"已保存 {len(market_list)} 条市场信息到数据库")

    def collect(self, force: bool = False):
        """执行一次完整采集流程"""
        logger.info("开始采集交易对静态信息...")
        market_list = self.fetch_target_markets(force=force)
        if market_list:
            self.save_to_db(market_list)
        logger.info("交易对静态信息采集完成")
        return market_list
