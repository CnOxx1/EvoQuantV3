from datetime import datetime, timezone

from pydantic import BaseModel, Field


def utc_now_naive() -> datetime:
    """返回不带 tzinfo 的 UTC 时间，兼容现有 SQLite 存储格式。"""

    return datetime.now(timezone.utc).replace(tzinfo=None)


class NewsSource(BaseModel):
    """新闻源配置。"""

    name: str = Field(..., description="新闻源名称")
    feed_url: str = Field(..., description="RSS/Atom 地址")
    fallback_feed_urls: list[str] = Field(
        default_factory=list,
        description="主地址失败时依次尝试的备用 feed 地址",
    )
    category: str | None = Field(default=None, description="默认分类")
    source_group: str | None = Field(default=None, description="来源分组")
    language: str = Field(default="en", description="默认语言")
    enabled: bool = Field(default=True, description="是否启用")
    tags: list[str] = Field(default_factory=list, description="源级别标签")


class NewsArticle(BaseModel):
    """标准化后的新闻条目。"""

    source: str = Field(..., description="新闻源名称")
    source_type: str = Field(default="rss", description="数据源类型，如 rss / atom")
    feed_url: str = Field(..., description="来源 feed 地址")
    category: str | None = Field(default=None, description="文章分类")
    title: str = Field(..., description="文章标题")
    summary: str | None = Field(default=None, description="文章摘要")
    content_text: str | None = Field(default=None, description="正文纯文本")
    url: str = Field(..., description="文章链接")
    url_hash: str = Field(..., description="规范化链接哈希，用于去重")
    author: str | None = Field(default=None, description="作者")
    published_at: datetime | None = Field(default=None, description="发布时间（UTC）")
    collected_at: datetime = Field(default_factory=utc_now_naive, description="采集时间（UTC）")
    language: str | None = Field(default=None, description="语言")
    relevance_symbols: list[str] = Field(default_factory=list, description="命中的目标币种")
    tags: list[str] = Field(default_factory=list, description="文章标签")
    image_url: str | None = Field(default=None, description="封面图链接")
    external_id: str | None = Field(default=None, description="源站唯一ID，如 guid / atom:id")
    raw_payload_json: str | None = Field(default=None, description="原始解析结果JSON")
