"""API 分页工具 — 游标分页 + 偏移分页 + 响应信封。

使用方式：
    from api.pagination import CursorParams, paginated_response, build_keyset_query

    @router.get("/items")
    def list_items(cursor: str = None, limit: int = Query(50, ge=1, le=1000)):
        params = CursorParams(cursor=cursor, limit=limit)
        sql, sql_params = build_keyset_query(
            base_sql="SELECT * FROM items WHERE symbol = ?",
            base_params=(symbol,),
            cursor_params=params,
            timestamp_col="timestamp",
            id_col="rowid",
        )
        rows = db.fetch_all(sql, sql_params)
        return paginated_response(rows, params, timestamp_col="timestamp", id_col="rowid")
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any, Optional

try:
    import orjson as _json_mod
    _json_dumps = lambda obj: _json_mod.dumps(obj).decode()
    _json_loads = _json_mod.loads
except ImportError:
    _json_dumps = lambda obj: json.dumps(obj, separators=(",", ":"))
    _json_loads = json.loads

from fastapi import Query

# 绝对上限，防止客户端滥用
ABSOLUTE_MAX_LIMIT = 1000
DEFAULT_LIMIT = 50


@dataclass
class CursorParams:
    """游标分页参数。"""

    cursor: Optional[str] = None
    limit: int = DEFAULT_LIMIT

    def __post_init__(self):
        self.limit = min(max(1, self.limit), ABSOLUTE_MAX_LIMIT)

    @property
    def decoded_cursor(self) -> Optional[dict[str, Any]]:
        if not self.cursor:
            return None
        try:
            payload = base64.urlsafe_b64decode(self.cursor + "==")
            return _json_loads(payload)
        except (ValueError, Exception):
            return None


@dataclass
class OffsetParams:
    """偏移分页参数。"""

    page: int = 1
    page_size: int = DEFAULT_LIMIT

    def __post_init__(self):
        self.page = max(1, self.page)
        self.page_size = min(max(1, self.page_size), ABSOLUTE_MAX_LIMIT)

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


def encode_cursor(timestamp: str, row_id: Any) -> str:
    """将 (timestamp, id) 编码为 opaque cursor。"""
    # v4.5.0: orjson 快速路径替代 json.dumps
    payload = _json_dumps({"ts": timestamp, "id": row_id})
    encoded = base64.urlsafe_b64encode(payload.encode()).rstrip(b"=")
    return encoded.decode()


def build_keyset_query(
    base_sql: str,
    base_params: tuple = (),
    cursor_params: Optional[CursorParams] = None,
    timestamp_col: str = "timestamp",
    id_col: str = "rowid",
    order: str = "DESC",
) -> tuple[str, tuple]:
    """在基础 SQL 上追加游标分页条件。

    返回 (完整 SQL, 参数元组)。
    """
    if cursor_params is None:
        cursor_params = CursorParams()

    params = list(base_params)
    cursor_clause = ""
    decoded = cursor_params.decoded_cursor

    if decoded and "ts" in decoded:
        if order.upper() == "DESC":
            cursor_clause = (
                f" AND ({timestamp_col} < ? OR "
                f"({timestamp_col} = ? AND {id_col} < ?))"
            )
        else:
            cursor_clause = (
                f" AND ({timestamp_col} > ? OR "
                f"({timestamp_col} = ? AND {id_col} > ?))"
            )
        params.extend([decoded["ts"], decoded["ts"], decoded["id"]])

    # fetch limit + 1 to detect has_more
    fetch_limit = cursor_params.limit + 1
    sql = (
        f"{base_sql}{cursor_clause} "
        f"ORDER BY {timestamp_col} {order}, {id_col} {order} "
        f"LIMIT ?"
    )
    params.append(fetch_limit)
    return sql, tuple(params)


def build_offset_query(
    base_sql: str,
    base_params: tuple = (),
    offset_params: Optional[OffsetParams] = None,
    order_by: str = "timestamp DESC",
) -> tuple[str, tuple]:
    """在基础 SQL 上追加偏移分页条件。"""
    if offset_params is None:
        offset_params = OffsetParams()

    params = list(base_params)
    sql = f"{base_sql} ORDER BY {order_by} LIMIT ? OFFSET ?"
    params.extend([offset_params.page_size, offset_params.offset])
    return sql, tuple(params)


def paginated_response(
    rows: list[Any],
    params: CursorParams,
    timestamp_col: str = "timestamp",
    id_col: str = "rowid",
    total_count: Optional[int] = None,
) -> dict[str, Any]:
    """将查询结果包装为分页响应信封。

    rows 应比 limit 多取一条（用于判断 has_more）。
    """
    has_more = len(rows) > params.limit
    data = rows[: params.limit]

    next_cursor: Optional[str] = None
    if has_more and data:
        last = data[-1]
        last_dict = dict(last) if hasattr(last, "keys") else last
        ts = last_dict.get(timestamp_col, "")
        rid = last_dict.get(id_col, "")
        next_cursor = encode_cursor(str(ts), rid)

    # 转为 plain dict
    data_dicts = [dict(r) if hasattr(r, "keys") else r for r in data]

    envelope: dict[str, Any] = {
        "data": data_dicts,
        "pagination": {
            "next_cursor": next_cursor,
            "has_more": has_more,
            "page_size": params.limit,
        },
    }
    if total_count is not None:
        envelope["pagination"]["total_count"] = total_count
    return envelope


def offset_paginated_response(
    rows: list[Any],
    params: OffsetParams,
    total_count: int,
) -> dict[str, Any]:
    """偏移分页响应信封。"""
    import math

    data_dicts = [dict(r) if hasattr(r, "keys") else r for r in rows]
    total_pages = math.ceil(total_count / params.page_size) if params.page_size else 1
    return {
        "data": data_dicts,
        "pagination": {
            "page": params.page,
            "page_size": params.page_size,
            "total_count": total_count,
            "total_pages": total_pages,
            "has_more": params.page < total_pages,
        },
    }
