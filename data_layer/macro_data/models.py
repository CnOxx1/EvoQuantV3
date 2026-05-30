import json
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, model_validator


def utc_now_naive() -> datetime:
    """返回不带 tzinfo 的 UTC 时间，兼容现有 SQLite 存储格式。"""

    return datetime.now(timezone.utc).replace(tzinfo=None)


class MacroFactorDefinition(BaseModel):
    """宏观因子目录定义。"""

    factor_id: str = Field(..., description="系统内部稳定因子 ID")
    name: str = Field(..., description="显示名称")
    category: str = Field(..., description="因子大类")
    factor_type: Literal["market_price", "macro_level"] = Field(
        ...,
        description="因子类型",
    )
    source_kind: Literal["yahoo_chart", "fred_csv"] = Field(
        ...,
        description="上游 adapter 类型",
    )
    description: str | None = Field(default=None, description="因子说明")
    default_interval: str = Field(default="1d", description="默认频率")
    supported_intervals: list[str] = Field(
        default_factory=lambda: ["1d"],
        description="支持的标准化频率",
    )
    unit: str | None = Field(default=None, description="单位")
    currency: str | None = Field(default="USD", description="计价币种")
    source_name: str = Field(..., description="上游来源名称")
    source_symbol: str = Field(..., description="上游来源符号/序列 ID")
    source_priority: Literal["primary", "fallback"] = Field(
        default="primary",
        description="来源优先级",
    )
    market_region: str | None = Field(default="US", description="所属市场区域")
    market_session: str | None = Field(default=None, description="市场时段")
    staleness_ttl_seconds: int = Field(
        default=86400,
        description="超过该时长可视为 stale",
    )
    is_intraday_enabled: bool = Field(default=False, description="是否启用小时级采集")
    enabled: bool = Field(default=True, description="当前是否参与采集")

    def to_catalog_tuple(self) -> tuple:
        return (
            self.factor_id,
            self.name,
            self.category,
            self.factor_type,
            self.description,
            self.default_interval,
            self.unit,
            self.currency,
            self.source_name,
            self.source_symbol,
            self.source_priority,
            self.market_region,
            self.market_session,
            self.staleness_ttl_seconds,
            int(self.is_intraday_enabled),
            int(self.enabled),
            json.dumps(
                {
                    "supported_intervals": self.supported_intervals,
                    "source_kind": self.source_kind,
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            utc_now_naive().isoformat(),
        )


class MacroTimeSeriesPoint(BaseModel):
    """标准化后的宏观因子时序点。"""

    factor_id: str = Field(..., description="系统内部稳定因子 ID")
    category: str = Field(..., description="因子大类")
    factor_type: Literal["market_price", "macro_level"] = Field(
        ...,
        description="因子类型",
    )
    interval: str = Field(..., description="标准化频率，例如 1h / 1d")
    observation_time: datetime = Field(..., description="观测时间（UTC）")
    session_date: str | None = Field(default=None, description="观测所属交易日")
    value: float | None = Field(default=None, description="统一读取值")
    open: float | None = Field(default=None, description="开盘价")
    high: float | None = Field(default=None, description="最高价")
    low: float | None = Field(default=None, description="最低价")
    close: float | None = Field(default=None, description="收盘价")
    volume: float | None = Field(default=None, description="成交量")
    unit: str | None = Field(default=None, description="单位")
    currency: str | None = Field(default=None, description="计价币种")
    source_name: str = Field(..., description="上游来源名称")
    source_symbol: str = Field(..., description="上游来源符号/序列 ID")
    source_priority: Literal["primary", "fallback"] = Field(
        default="primary",
        description="来源优先级",
    )
    available_at: datetime | None = Field(default=None, description="对外可用时间")
    is_revision: bool = Field(default=False, description="是否为修订值")
    revision_seq: int = Field(default=0, description="修订序号")
    quality_flag: Literal["ok", "stale", "partial", "fallback"] = Field(
        default="ok",
        description="数据质量标记",
    )
    is_market_open: bool | None = Field(default=None, description="采集时市场是否在交易")
    ingest_run_id: str | None = Field(default=None, description="本次采集批次 ID")
    collected_at: datetime = Field(default_factory=utc_now_naive, description="采集时间")
    raw_payload_json: str | None = Field(default=None, description="原始 payload JSON")

    @model_validator(mode="after")
    def _normalize_fields(self):
        if self.observation_time.tzinfo is not None:
            self.observation_time = self.observation_time.astimezone(
                timezone.utc
            ).replace(tzinfo=None)

        if self.available_at is None:
            self.available_at = self.observation_time
        elif self.available_at.tzinfo is not None:
            self.available_at = self.available_at.astimezone(
                timezone.utc
            ).replace(tzinfo=None)

        if self.factor_type == "market_price":
            if self.value is None:
                self.value = self.close
            if self.value is None:
                raise ValueError("market_price 因子必须至少提供 close 或 value")
        elif self.value is None:
            raise ValueError("macro_level 因子必须提供 value")

        if self.session_date is None:
            self.session_date = self.observation_time.date().isoformat()

        if self.collected_at.tzinfo is not None:
            self.collected_at = self.collected_at.astimezone(
                timezone.utc
            ).replace(tzinfo=None)
        return self

    def history_db_tuple(self) -> tuple:
        return (
            self.factor_id,
            self.category,
            self.factor_type,
            self.interval,
            self.observation_time.isoformat(),
            self.session_date,
            self.value,
            self.open,
            self.high,
            self.low,
            self.close,
            self.volume,
            self.unit,
            self.currency,
            self.source_name,
            self.source_symbol,
            self.source_priority,
            self.available_at.isoformat() if self.available_at else None,
            int(self.is_revision),
            self.revision_seq,
            self.quality_flag,
            None if self.is_market_open is None else int(self.is_market_open),
            self.ingest_run_id,
            self.collected_at.isoformat(),
            self.raw_payload_json,
        )

    def latest_db_tuple(self) -> tuple:
        return (
            self.factor_id,
            self.factor_type,
            self.interval,
            self.observation_time.isoformat(),
            self.value,
            self.open,
            self.high,
            self.low,
            self.close,
            self.unit,
            self.currency,
            self.source_name,
            self.source_symbol,
            self.source_priority,
            self.quality_flag,
            None if self.is_market_open is None else int(self.is_market_open),
            self.collected_at.isoformat(),
        )
