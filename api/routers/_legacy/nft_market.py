"""NFT Market 路由 — NFT 市场数据与收藏品统计分析端点。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from api.dependencies import get_market_db

router = APIRouter(prefix="/nft-market", tags=["nft-market"])


@router.get("/collections")
def get_collections(
    limit: int = Query(20, ge=1, le=200, description="返回条数"),
) -> dict[str, Any]:
    """热门 NFT 收藏品（按24小时交易量排序）。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT * FROM nft_collection_stats ORDER BY volume_24h_eth DESC LIMIT ?",
        (limit,),
    )
    return {"count": len(rows), "collections": rows}


@router.get("/overview")
def get_overview() -> dict[str, Any]:
    """NFT 市场整体指标概览。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT * FROM nft_market_metrics ORDER BY timestamp DESC LIMIT 1",
        (),
    )
    if not rows:
        return {"status": "no_data"}
    return {"overview": rows[0]}


@router.get("/collection")
def get_collection(
    collection: str = Query(..., description="收藏品名称"),
) -> dict[str, Any]:
    """指定收藏品的详细统计。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT * FROM nft_collection_stats WHERE collection = ? ORDER BY timestamp DESC LIMIT 1",
        (collection,),
    )
    if not rows:
        return {"status": "no_data", "collection": collection}
    return {"collection": collection, "stats": rows[0]}


@router.get("/history")
def get_history(
    limit: int = Query(50, ge=1, le=500, description="返回条数"),
) -> dict[str, Any]:
    """历史市场指标。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT * FROM nft_market_metrics ORDER BY timestamp DESC LIMIT ?",
        (limit,),
    )
    return {"count": len(rows), "history": rows}


@router.get("/context")
def get_nft_market_context() -> dict[str, Any]:
    """NFT 市场 AI 上下文 bundle。"""
    from data_layer.nft_market_data.service import NftMarketDataService
    service = NftMarketDataService()
    service.init_storage()
    bundle = service.load_latest_context_bundle()
    service.close()
    return bundle
