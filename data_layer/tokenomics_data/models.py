import json
from datetime import datetime, timezone

from pydantic import BaseModel, Field, model_validator


def utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def build_dimensions_key(dimensions: dict[str, object] | None) -> str:
    if not dimensions:
        return "base"
    parts: list[str] = []
    for key in sorted(dimensions):
        value = dimensions[key]
        if isinstance(value, bool):
            value_text = str(int(value))
        else:
            value_text = str(value)
        parts.append(f"{key}={value_text}")
    return "|".join(parts) or "base"


def dump_json(payload: dict[str, object] | list[object] | None) -> str | None:
    if payload is None:
        return None
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


class TokenomicsSourceDefinition(BaseModel):
    source_name: str = Field(..., description="来源 ID")
    name: str = Field(..., description="来源显示名")
    description: str = Field(..., description="来源说明")
    collector_key: str = Field(..., description="collector 路由键")
    primary_factor_id: str = Field(..., description="主因子 ID")
    entity_type: str = Field(..., description="实体类型")
    default_interval: str = Field(default="1d", description="默认频率")
    endpoint: str | None = Field(default=None, description="上游接口地址")
    enabled: bool = Field(default=True, description="是否启用")
    params: dict[str, object] = Field(default_factory=dict, description="固定查询参数")
    raw_meta: dict[str, object] = Field(default_factory=dict, description="扩展元数据")


class TokenomicsFactorDefinition(BaseModel):
    factor_id: str = Field(..., description="系统内部稳定因子 ID")
    name: str = Field(..., description="显示名称")
    category: str = Field(..., description="因子大类")
    factor_type: str = Field(..., description="指标语义类型")
    entity_scope: str = Field(..., description="实体范围")
    entity_type: str = Field(..., description="实体类型")
    description: str | None = Field(default=None, description="因子说明")
    default_interval: str = Field(default="1d", description="默认频率")
    unit: str | None = Field(default=None, description="单位")
    source_name: str = Field(..., description="上游来源名称")
    source_symbol: str = Field(..., description="上游来源符号")
    source_priority: str = Field(default="primary", description="来源优先级")
    config_version: str = Field(default="v1", description="配置版本")
    staleness_ttl_seconds: int = Field(default=86400, description="新鲜度 TTL")
    enabled: bool = Field(default=True, description="当前是否启用")
    raw_meta: dict[str, object] = Field(default_factory=dict, description="扩展元数据")

    def to_catalog_tuple(self) -> tuple:
        return (
            self.factor_id,
            self.name,
            self.category,
            self.factor_type,
            self.entity_scope,
            self.entity_type,
            self.description,
            self.default_interval,
            self.unit,
            self.source_name,
            self.source_symbol,
            self.source_priority,
            self.config_version,
            self.staleness_ttl_seconds,
            int(self.enabled),
            dump_json(self.raw_meta),
            utc_now_naive().isoformat(),
        )


class TokenomicsTimeSeriesPoint(BaseModel):
    factor_id: str = Field(..., description="系统内部稳定因子 ID")
    category: str = Field(..., description="因子大类")
    factor_type: str = Field(..., description="指标语义类型")
    entity_type: str = Field(..., description="实体类型")
    entity_key: str = Field(..., description="实体键")
    interval: str = Field(..., description="标准化频率")
    observation_time: datetime = Field(..., description="观测时间（UTC）")
    value: float = Field(..., description="统一读取值")
    unit: str | None = Field(default=None, description="单位")
    quality_flag: str = Field(default="ok", description="质量标记")
    dimensions_key: str | None = Field(default=None, description="维度唯一键")
    dimensions_json: dict[str, object] | None = Field(default=None, description="维度信息")
    config_version: str = Field(default="v1", description="配置版本")
    source_name: str = Field(..., description="上游来源名称")
    source_symbol: str = Field(..., description="上游来源符号")
    collected_at: datetime = Field(default_factory=utc_now_naive, description="采集时间")
    raw_payload_json: str | None = Field(default=None, description="原始 payload JSON")

    @model_validator(mode="after")
    def _normalize_fields(self):
        if self.observation_time.tzinfo is not None:
            self.observation_time = self.observation_time.astimezone(
                timezone.utc
            ).replace(tzinfo=None)
        if self.collected_at.tzinfo is not None:
            self.collected_at = self.collected_at.astimezone(
                timezone.utc
            ).replace(tzinfo=None)
        self.entity_key = self.entity_key.strip().upper()
        if self.dimensions_json is None:
            self.dimensions_json = {}
        if not self.dimensions_key:
            self.dimensions_key = build_dimensions_key(self.dimensions_json)
        return self

    def history_db_tuple(self) -> tuple:
        return (
            self.factor_id,
            self.category,
            self.factor_type,
            self.entity_type,
            self.entity_key,
            self.interval,
            self.observation_time.isoformat(),
            self.value,
            self.unit,
            self.quality_flag,
            self.dimensions_key,
            dump_json(self.dimensions_json),
            self.config_version,
            self.source_name,
            self.source_symbol,
            self.raw_payload_json,
            self.collected_at.isoformat(),
        )

    def latest_db_tuple(self) -> tuple:
        return self.history_db_tuple()


class TokenUnlockEvent(BaseModel):
    asset: str = Field(..., description="资产键")
    event_type: str = Field(default="unlock", description="事件类型")
    scheduled_at: datetime = Field(..., description="计划时间")
    unlock_amount: float | None = Field(default=None, description="解锁数量")
    unlock_value_usd: float | None = Field(default=None, description="解锁美元价值")
    unlock_pct_float: float | None = Field(default=None, description="解锁占流通盘比例")
    beneficiary_group: str | None = Field(default=None, description="受益对象组")
    status: str = Field(default="scheduled", description="状态")
    source_name: str = Field(..., description="来源")
    source_url: str | None = Field(default=None, description="来源链接")
    raw_payload_json: str | None = Field(default=None, description="原始 payload")
    collected_at: datetime = Field(default_factory=utc_now_naive, description="采集时间")

    @model_validator(mode="after")
    def _normalize_fields(self):
        self.asset = self.asset.strip().upper()
        if self.scheduled_at.tzinfo is not None:
            self.scheduled_at = self.scheduled_at.astimezone(timezone.utc).replace(
                tzinfo=None
            )
        if self.collected_at.tzinfo is not None:
            self.collected_at = self.collected_at.astimezone(timezone.utc).replace(
                tzinfo=None
            )
        return self

    def to_db_tuple(self) -> tuple:
        return (
            self.asset,
            self.event_type,
            self.scheduled_at.isoformat(),
            self.unlock_amount,
            self.unlock_value_usd,
            self.unlock_pct_float,
            self.beneficiary_group,
            self.status,
            self.source_name,
            self.source_url,
            self.raw_payload_json,
            self.collected_at.isoformat(),
        )
