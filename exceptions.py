"""EvoQuant 项目级异常层次结构。

设计原则：
- 每层有对应的基类，方便按层粒度 catch
- 所有异常携带可选 error_code 和 context，便于结构化日志和 API 序列化
- 保持轻量，不强制所有模块立即迁移
"""

from __future__ import annotations


class EvoQuantError(Exception):
    """项目根异常。所有自定义异常继承此类。"""

    error_code: str = "EVOQUANT_ERROR"

    def __init__(self, message: str = "", *, context: dict | None = None):
        self.message = message
        self.context = context or {}
        super().__init__(message)

    def __str__(self) -> str:
        if self.context:
            ctx = ", ".join(f"{k}={v!r}" for k, v in self.context.items())
            return f"[{self.error_code}] {self.message} ({ctx})"
        return f"[{self.error_code}] {self.message}"


# ─── 数据层 ───────────────────────────────────────────────

class DataLayerError(EvoQuantError):
    """数据采集层通用异常。"""
    error_code = "DATA_LAYER_ERROR"


class DataAcquisitionError(DataLayerError):
    """外部数据源获取失败（网络超时、API 错误等）。"""
    error_code = "DATA_ACQUISITION_FAILED"


class DataValidationError(DataLayerError):
    """采集数据格式/schema 校验失败。"""
    error_code = "DATA_VALIDATION_FAILED"


class DataSourceUnavailableError(DataLayerError):
    """数据源暂时不可用（熔断、限流、维护）。"""
    error_code = "DATA_SOURCE_UNAVAILABLE"


# ─── 逻辑层 ───────────────────────────────────────────────

class LogicLayerError(EvoQuantError):
    """逻辑分析层通用异常。"""
    error_code = "LOGIC_LAYER_ERROR"


class AnalysisError(LogicLayerError):
    """分析计算过程中出错（数据不足、算法异常等）。"""
    error_code = "ANALYSIS_FAILED"


class PipelinePhaseError(LogicLayerError):
    """管道某阶段执行失败。"""
    error_code = "PIPELINE_PHASE_FAILED"


# ─── 数据库层 ─────────────────────────────────────────────

class DatabaseError(EvoQuantError):
    """数据库操作异常。"""
    error_code = "DATABASE_ERROR"


class SchemaError(DatabaseError):
    """表结构/迁移异常。"""
    error_code = "SCHEMA_ERROR"


class QueryError(DatabaseError):
    """查询执行失败。"""
    error_code = "QUERY_ERROR"


# ─── API 层 ───────────────────────────────────────────────

class APIError(EvoQuantError):
    """API 层通用异常，携带 HTTP 状态码。"""
    error_code = "API_ERROR"
    status_code: int = 500

    def __init__(
        self,
        message: str = "",
        *,
        status_code: int | None = None,
        context: dict | None = None,
    ):
        if status_code is not None:
            self.status_code = status_code
        super().__init__(message, context=context)


class NotFoundError(APIError):
    """资源不存在。"""
    error_code = "NOT_FOUND"
    status_code = 404


class ValidationError(APIError):
    """请求参数校验失败。"""
    error_code = "VALIDATION_ERROR"
    status_code = 422


class RateLimitError(APIError):
    """请求频率超限。"""
    error_code = "RATE_LIMIT_EXCEEDED"
    status_code = 429
