import json
from datetime import datetime, timezone

from pydantic import BaseModel, Field, model_validator


def utc_now_naive() -> datetime:
    """返回不带 tzinfo 的 UTC 时间，兼容现有 SQLite 存储格式。"""

    return datetime.now(timezone.utc).replace(tzinfo=None)


def build_dimensions_key(dimensions: dict[str, object] | None) -> str:
    """将 dimensions dict 规范化为稳定的唯一键片段。"""

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


class AlternativeFactorDefinition(BaseModel):
    """补充特征因子目录定义。"""

    factor_id: str = Field(..., description="系统内部稳定因子 ID")
    name: str = Field(..., description="显示名称")
    category: str = Field(..., description="因子大类")
    factor_type: str = Field(..., description="指标语义类型")
    entity_scope: str = Field(..., description="实体范围，例如 repo_group / stablecoin")
    entity_type: str = Field(..., description="实体类型")
    description: str | None = Field(default=None, description="因子说明")
    default_interval: str = Field(default="1d", description="默认频率")
    unit: str | None = Field(default=None, description="单位")
    source_name: str = Field(..., description="上游来源名称")
    source_symbol: str = Field(..., description="上游来源符号/系列 ID")
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


class AlternativeTimeSeriesPoint(BaseModel):
    """标准化后的补充特征时序点。"""

    factor_id: str = Field(..., description="系统内部稳定因子 ID")
    category: str = Field(..., description="因子大类")
    factor_type: str = Field(..., description="指标语义类型")
    entity_type: str = Field(..., description="实体类型")
    entity_key: str = Field(..., description="实体键")
    interval: str = Field(..., description="标准化频率，例如 1h / 1d")
    observation_time: datetime = Field(..., description="观测时间（UTC）")
    value: float = Field(..., description="统一读取值")
    unit: str | None = Field(default=None, description="单位")
    quality_flag: str = Field(default="ok", description="质量标记")
    dimensions_key: str | None = Field(default=None, description="维度唯一键")
    dimensions_json: dict[str, object] | None = Field(
        default=None,
        description="维度信息",
    )
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

        if self.dimensions_json is None:
            self.dimensions_json = {}
        if not self.dimensions_key:
            self.dimensions_key = build_dimensions_key(self.dimensions_json)
        if not self.config_version:
            self.config_version = "v1"
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
