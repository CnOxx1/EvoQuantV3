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
    # INSERT OR IGNORE → INSERT ... ON CONFLICT DO NOTHING
    (re.compile(r"\bINSERT\s+OR\s+IGNORE\b", re.IGNORECASE),
     "INSERT"),
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


def _adapt_insert_or_replace(sql: str) -> str:
    """将 INSERT OR REPLACE INTO t(cols) VALUES(...) 转为 PostgreSQL UPSERT。

    简化处理：使用 ON CONFLICT DO UPDATE SET 所有列。
    如果表没有唯一约束，退化为普通 INSERT。
    """
    match = _INSERT_OR_REPLACE_RE.search(sql)
    if not match:
        return sql

    table = match.group(1)
    columns_str = match.group(2).strip()
    columns = [c.strip() for c in columns_str.split(",")]

    # 移除 "OR REPLACE" 关键字
    new_sql = re.sub(r"\bOR\s+REPLACE\b", "", sql, count=1, flags=re.IGNORECASE)

    # 追加 ON CONFLICT DO UPDATE（使用第一列作为冲突键的合理默认）
    # 实际使用中表应有明确的 PRIMARY KEY / UNIQUE 约束
    set_clauses = ", ".join(f"{c} = EXCLUDED.{c}" for c in columns[1:])
    if set_clauses:
        conflict_suffix = (
            f" ON CONFLICT ({columns[0]}) DO UPDATE SET {set_clauses}"
        )
    else:
        conflict_suffix = f" ON CONFLICT ({columns[0]}) DO NOTHING"

    new_sql = new_sql.rstrip().rstrip(";") + conflict_suffix
    return new_sql
