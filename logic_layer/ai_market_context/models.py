import json
from datetime import datetime, timezone
from typing import ClassVar

from pydantic import BaseModel, Field


def utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class AIMarketContextSnapshot(BaseModel):
    entity_key: str = Field(..., description="资产键")
    snapshot_time: datetime = Field(default_factory=utc_now_naive, description="快照时间")
    coverage_score: float = Field(default=0.0, description="覆盖率")
    data_quality_flag: str = Field(default="partial", description="质量标记")
    bundle: dict[str, object] = Field(default_factory=dict, description="完整 bundle")

    TABLE_COLUMNS: ClassVar[list[str]] = [
        "entity_key",
        "snapshot_time",
        "coverage_score",
        "data_quality_flag",
        "bundle_json",
    ]

    def to_db_tuple(self) -> tuple:
        return (
            self.entity_key,
            self.snapshot_time.isoformat(),
            self.coverage_score,
            self.data_quality_flag,
            json.dumps(self.bundle, ensure_ascii=False, separators=(",", ":")),
        )
