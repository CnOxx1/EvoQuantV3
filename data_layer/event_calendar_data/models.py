import hashlib
import json
from datetime import datetime, timezone

from pydantic import BaseModel, Field, model_validator


VALID_EVENT_STATUSES = {"scheduled", "updated", "canceled", "completed"}


def utc_now_naive() -> datetime:
    """返回不带 tzinfo 的 UTC 时间，兼容现有 SQLite 存储格式。"""

    return datetime.now(timezone.utc).replace(tzinfo=None)


def dump_json(payload: dict[str, object] | list[object] | None) -> str | None:
    if payload is None:
        return None
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def normalize_tags(values: list[str] | None) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for value in values or []:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        normalized.append(text)
    return normalized


def build_event_key(
    source_name: str,
    event_type: str,
    scheduled_at: datetime,
    title: str,
    symbol: str,
    external_id: str | None = None,
) -> str:
    if external_id:
        stable_text = "|".join(
            [
                source_name.strip().lower(),
                event_type.strip().lower(),
                external_id.strip().lower(),
            ]
        )
    else:
        stable_text = "|".join(
            [
                source_name.strip().lower(),
                event_type.strip().lower(),
                scheduled_at.isoformat(),
                title.strip().lower(),
                symbol.strip().upper(),
            ]
        )
    return hashlib.sha1(stable_text.encode("utf-8")).hexdigest()


class EventCalendarSource(BaseModel):
    """事件日历来源定义。"""

    name: str = Field(..., description="来源名称")
    event_type: str = Field(..., description="默认事件类型")
    endpoint: str | None = Field(default=None, description="上游接口地址")
    adapter: str = Field(default="normalized_json", description="解析适配器类型")
    description: str | None = Field(default=None, description="来源说明")
    enabled: bool = Field(default=True, description="当前是否启用")
    default_symbol: str = Field(default="MARKET", description="默认关联实体")
    timezone: str = Field(default="UTC", description="默认时区")
    tags: list[str] = Field(default_factory=list, description="来源级标签")
    params: dict[str, object] = Field(default_factory=dict, description="固定查询参数")

    @model_validator(mode="after")
    def _normalize_fields(self):
        self.default_symbol = (self.default_symbol or "MARKET").strip().upper()
        self.tags = normalize_tags(self.tags)
        if not self.adapter:
            self.adapter = "normalized_json"
        return self


class EventCalendarEvent(BaseModel):
    """标准化后的日历事件。"""

    event_key: str | None = Field(default=None, description="稳定唯一键")
    event_type: str = Field(..., description="事件类型")
    title: str = Field(..., description="事件标题")
    description: str | None = Field(default=None, description="事件描述")
    symbol: str = Field(default="MARKET", description="关联资产或 MARKET")
    scheduled_at: datetime = Field(..., description="计划发生时间（UTC）")
    timezone: str = Field(default="UTC", description="原始时区")
    importance_score: float | None = Field(default=None, description="重要度")
    source_name: str = Field(..., description="来源名称")
    status: str = Field(default="scheduled", description="事件状态")
    source_url: str | None = Field(default=None, description="上游事件 URL")
    external_id: str | None = Field(default=None, description="上游事件唯一 ID")
    tags: list[str] = Field(default_factory=list, description="事件标签")
    collected_at: datetime = Field(default_factory=utc_now_naive, description="采集时间")
    raw_payload_json: str | None = Field(default=None, description="原始 payload JSON")

    @model_validator(mode="after")
    def _normalize_fields(self):
        if self.scheduled_at.tzinfo is not None:
            self.scheduled_at = self.scheduled_at.astimezone(
                timezone.utc
            ).replace(tzinfo=None)

        if self.collected_at.tzinfo is not None:
            self.collected_at = self.collected_at.astimezone(
                timezone.utc
            ).replace(tzinfo=None)

        self.event_type = self.event_type.strip().lower()
        self.status = self.status.strip().lower()
        if self.status not in VALID_EVENT_STATUSES:
            raise ValueError(f"未知事件状态: {self.status}")

        self.symbol = (self.symbol or "MARKET").strip().upper()
        self.tags = normalize_tags(self.tags)

        if not self.event_key:
            self.event_key = build_event_key(
                source_name=self.source_name,
                event_type=self.event_type,
                scheduled_at=self.scheduled_at,
                title=self.title,
                symbol=self.symbol,
                external_id=self.external_id,
            )
        return self

    def db_tuple(self) -> tuple:
        return (
            self.event_key,
            self.event_type,
            self.title,
            self.description,
            self.symbol,
            self.scheduled_at.isoformat(),
            self.timezone,
            self.importance_score,
            self.source_name,
            self.status,
            self.source_url,
            self.external_id,
            dump_json(self.tags),
            self.collected_at.isoformat(),
            self.raw_payload_json,
        )
