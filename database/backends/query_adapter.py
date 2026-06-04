"""QueryAdapter — SQL 方言适配器：SQLite ? ↔ PostgreSQL %s 占位符转换。"""

from __future__ import annotations

import re


# SQLite 特有语法 → PostgreSQL 等价物的映射
_SQLITE_TO_PG_REPLACEMENTS = [
    # AUTOINCREMENT → SERIAL (handled at DDL level, not here)
    (re.compile(r"\bINTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT\b", re.IGNORECASE),
     "SERIAL PRIMARY KEY"),
    # datetime('now', ...) → NOW() + interval
    (re.compile(r"datetime\('now'\)", re.IGNORECASE), "NOW()"),
    (re.compile(r"datetime\('now',\s*'(-?\d+)\s+day'\)", re.IGNORECASE),
     r"NOW() + INTERVAL '\1 day'"),
    (re.compile(r"datetime\('now',\s*'(-?\d+)\s+hour'\)", re.IGNORECASE),
     r"NOW() + INTERVAL '\1 hour'"),
    # INSERT OR REPLACE → INSERT ... ON CONFLICT DO UPDATE
    # (complex; handled separately below)
    # INSERT OR IGNORE → INSERT ... ON CONFLICT DO NOTHING (handled separately below)

]

# 占位符转换的正则：匹配 ? 但排除字符串内的
_PLACEHOLDER_RE = re.compile(
    r"""
    '(?:[^'\\]|\\.)*'  |  # 单引号字符串
    "(?:[^"\\]|\\.)*"  |  # 双引号字符串
    (\?)                   # 裸 ? 占位符
    """,
    re.VERBOSE,
)


# 转义 SQL 中字面量 % 的正则（排除字符串内的）
# 注意：psycopg2 在接收 params 参数时会对整个 SQL 做 % 格式化，
# 即使 % 在 SQL 单引号内也会被解释。因此需要转义所有非 %s 的 %。


def _escape_percent_literals(sql: str) -> str:
    """将 SQL 中所有 % 转义为 %%（psycopg2 要求），后续 ? → %s 会生成正确的 %s。

    注意：此函数在 ? → %s 转换之前调用，所以此时 SQL 中不应有 %s 占位符。
    """
    return sql.replace("%", "%%")


def adapt_query(sql: str) -> str:
    """将 SQLite 风格 SQL 转换为 PostgreSQL 兼容格式。

    - ? → %s 占位符
    - SQLite 函数 → PG 等价物
    """
    # 先替换 SQLite 特有语法
    for pattern, replacement in _SQLITE_TO_PG_REPLACEMENTS:
        sql = pattern.sub(replacement, sql)

    # INSERT OR REPLACE → INSERT ... ON CONFLICT DO UPDATE
    sql = _adapt_insert_or_replace(sql)

    # INSERT OR IGNORE → INSERT ... ON CONFLICT DO NOTHING
    sql = _adapt_insert_or_ignore(sql)

    # 先将 SQL 中已有的 % 转义为 %%（psycopg2 要求），排除字符串内的
    sql = _escape_percent_literals(sql)

    # 占位符转换 ? → %s（排除字符串内的 ?）
    counter = [0]

    def _replace_placeholder(match: re.Match) -> str:
        if match.group(1):  # 是裸 ? 占位符
            counter[0] += 1
            return "%s"
        return match.group(0)  # 保持字符串原样

    sql = _PLACEHOLDER_RE.sub(_replace_placeholder, sql)
    return sql


# INSERT OR REPLACE 的正则
_INSERT_OR_REPLACE_RE = re.compile(
    r"\bINSERT\s+OR\s+REPLACE\s+INTO\s+(\w+)\s*\(([^)]+)\)",
    re.IGNORECASE,
)

# PostgreSQL 保留字列表（需要双引号）
_PG_RESERVED_WORDS = frozenset([
    "timestamp", "time", "date", "interval", "order", "group",
    "user", "table", "column", "index", "type", "select", "from",
    "where", "limit", "offset", "all", "default", "check",
])


def _quote_if_reserved(col: str) -> str:
    """如果列名是 PostgreSQL 保留字，加双引号。"""
    if col.lower() in _PG_RESERVED_WORDS:
        return f'"{col}"'
    return col


def _adapt_insert_or_replace(sql: str) -> str:
    """将 INSERT OR REPLACE INTO t(cols) VALUES(...) 转为 PostgreSQL UPSERT。

    策略：移除 OR REPLACE 关键字，追加 ON CONFLICT DO UPDATE。
    冲突键选择逻辑：
    1. 跳过 id 列（SERIAL 自增）
    2. 如果列中包含已知的唯一键模式（symbol+exchange+timestamp 等），使用它们
    3. 否则退化为 ON CONFLICT DO NOTHING（避免报错）
    """
    match = _INSERT_OR_REPLACE_RE.search(sql)
    if not match:
        return sql

    table = match.group(1)
    columns_str = match.group(2).strip()
    columns = [c.strip() for c in columns_str.split(",")]

    # 移除 "OR REPLACE" 关键字
    new_sql = re.sub(r"\bOR\s+REPLACE\b", "", sql, count=1, flags=re.IGNORECASE)

    # 跳过 id 列来确定冲突键
    non_id_cols = [c for c in columns if c.lower() != "id"]

    # 尝试推断冲突键（基于常见的唯一键模式）
    conflict_cols = _infer_conflict_columns(table, non_id_cols)

    if conflict_cols:
        # 更新除冲突键和 id 之外的所有列
        update_cols = [c for c in columns if c not in conflict_cols and c.lower() != "id"]
        quoted_conflict = ", ".join(_quote_if_reserved(c) for c in conflict_cols)
        if update_cols:
            set_clauses = ", ".join(
                f"{_quote_if_reserved(c)} = EXCLUDED.{_quote_if_reserved(c)}" for c in update_cols
            )
            conflict_suffix = (
                f" ON CONFLICT ({quoted_conflict}) DO UPDATE SET {set_clauses}"
            )
        else:
            conflict_suffix = f" ON CONFLICT ({quoted_conflict}) DO NOTHING"
    else:
        # 无法推断冲突键，使用 DO NOTHING 避免报错
        conflict_suffix = " ON CONFLICT DO NOTHING"

    new_sql = new_sql.rstrip().rstrip(";") + conflict_suffix
    return new_sql


# INSERT OR IGNORE 的正则
_INSERT_OR_IGNORE_RE = re.compile(
    r"\bINSERT\s+OR\s+IGNORE\s+INTO\b",
    re.IGNORECASE,
)


def _adapt_insert_or_ignore(sql: str) -> str:
    """将 INSERT OR IGNORE INTO ... 转为 INSERT INTO ... ON CONFLICT DO NOTHING。"""
    if not _INSERT_OR_IGNORE_RE.search(sql):
        return sql
    new_sql = re.sub(r"\bOR\s+IGNORE\b", "", sql, count=1, flags=re.IGNORECASE)
    new_sql = new_sql.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"
    return new_sql


# 常见唯一键模式（表名 → 冲突列）
_KNOWN_CONFLICT_KEYS: dict[str, list[str]] = {}


def _infer_conflict_columns(table: str, columns: list[str]) -> list[str]:
    """推断表的冲突键列。"""
    # 如果有已知映射，直接使用
    if table in _KNOWN_CONFLICT_KEYS:
        return _KNOWN_CONFLICT_KEYS[table]

    cols_lower = [c.lower() for c in columns]

    # 通用模式：factor_id 类的表
    if "factor_id" in cols_lower:
        return ["factor_id"]

    # 通用模式：event_key
    if "event_key" in cols_lower:
        return ["event_key"]

    # 通用模式：url_hash
    if "url_hash" in cols_lower:
        return ["url_hash"]

    # 通用模式：txid + collected_at
    if "txid" in cols_lower and "collected_at" in cols_lower:
        return ["txid", "collected_at"]

    # 通用模式：symbol + exchange + timestamp + side + price_level (orderbook depth)
    if all(c in cols_lower for c in ["symbol", "exchange", "timestamp", "side", "price_level"]):
        return ["symbol", "exchange", "timestamp", "side", "price_level"]

    # 通用模式：symbol + exchange + market_type + interval + open_time
    if all(c in cols_lower for c in ["symbol", "exchange", "market_type", "interval", "open_time"]):
        return ["symbol", "exchange", "market_type", "interval", "open_time"]

    # 通用模式：symbol + exchange + market_type + interval + timestamp
    if all(c in cols_lower for c in ["symbol", "exchange", "market_type", "interval", "timestamp"]):
        return ["symbol", "exchange", "market_type", "interval", "timestamp"]

    # 通用模式：symbol + exchange + market_type + interval
    if all(c in cols_lower for c in ["symbol", "exchange", "market_type", "interval"]):
        return ["symbol", "exchange", "market_type", "interval"]

    # 通用模式：symbol + exchange + timeframe + open_time
    if all(c in cols_lower for c in ["symbol", "exchange", "timeframe", "open_time"]):
        return ["symbol", "exchange", "timeframe", "open_time"]

    # 通用模式：symbol + exchange + timestamp + side
    if all(c in cols_lower for c in ["symbol", "exchange", "timestamp", "side"]):
        return ["symbol", "exchange", "timestamp", "side"]

    # 通用模式：symbol + exchange + timestamp
    if all(c in cols_lower for c in ["symbol", "exchange", "timestamp"]):
        return ["symbol", "exchange", "timestamp"]

    # 通用模式：symbol + timeframe + open_time
    if all(c in cols_lower for c in ["symbol", "timeframe", "open_time"]):
        return ["symbol", "timeframe", "open_time"]

    # 通用模式：symbol + exchange
    if "symbol" in cols_lower and "exchange" in cols_lower:
        return ["symbol", "exchange"]

    # 通用模式：protocol + timestamp + hf_bucket
    if all(c in cols_lower for c in ["protocol", "timestamp", "hf_bucket"]):
        return ["protocol", "timestamp", "hf_bucket"]

    # 通用模式：有 asset 列的表
    if "asset" in cols_lower and "event_type" in cols_lower and "scheduled_at" in cols_lower:
        return ["asset", "event_type", "scheduled_at"]

    # 通用模式：asset + tx_hash + timestamp
    if all(c in cols_lower for c in ["asset", "tx_hash", "timestamp"]):
        return ["asset", "tx_hash", "timestamp"]

    # 通用模式：asset + chain + timestamp
    if all(c in cols_lower for c in ["asset", "chain", "timestamp"]):
        return ["asset", "chain", "timestamp"]

    # 通用模式：address + timestamp
    if "address" in cols_lower and "timestamp" in cols_lower:
        return ["address", "timestamp"]

    # 通用模式：address + date
    if "address" in cols_lower and "date" in cols_lower:
        return ["address", "date"]

    # 无法推断，返回空（将使用 DO NOTHING）
    return []
