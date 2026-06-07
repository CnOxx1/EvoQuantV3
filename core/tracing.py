"""OpenTelemetry 分布式追踪集成（可选启用）。"""

from __future__ import annotations

import os
from loguru import logger


OTEL_ENABLED = os.environ.get("OTEL_ENABLED", "false").lower() in ("1", "true", "yes")
OTEL_SERVICE_NAME = os.environ.get("OTEL_SERVICE_NAME", "evoquant")


def init_tracing(app=None) -> bool:
    """初始化 OpenTelemetry 追踪。返回是否成功启用。

    环境变量:
        OTEL_ENABLED: 是否启用追踪 (默认 false)
        OTEL_SERVICE_NAME: 服务名称 (默认 evoquant)
        OTEL_EXPORTER_OTLP_ENDPOINT: OTLP 导出端点 (可选，未设置时使用控制台导出)
    """
    if not OTEL_ENABLED:
        logger.debug("OpenTelemetry 追踪已禁用 (OTEL_ENABLED=false)")
        return False

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import (
            BatchSpanProcessor,
            ConsoleSpanExporter,
        )
    except ImportError:
        logger.warning(
            "OpenTelemetry 依赖未安装，请执行: "
            "pip install opentelemetry-api opentelemetry-sdk"
        )
        return False

    resource = Resource.create({"service.name": OTEL_SERVICE_NAME})
    provider = TracerProvider(resource=resource)

    # 根据环境变量选择导出器
    otlp_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    if otlp_endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                OTLPSpanExporter,
            )
            exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
            logger.info("OpenTelemetry OTLP 导出器已配置: {}", otlp_endpoint)
        except ImportError:
            logger.warning("OTLP 导出器未安装，回退到控制台导出")
            exporter = ConsoleSpanExporter()
    else:
        exporter = ConsoleSpanExporter()

    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    # 自动注入 FastAPI 追踪
    if app is not None:
        try:
            from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
            FastAPIInstrumentor.instrument_app(app)
            logger.info("FastAPI OpenTelemetry 自动注入已启用")
        except ImportError:
            logger.warning(
                "fastapi instrumentation 未安装: "
                "pip install opentelemetry-instrumentation-fastapi"
            )

    logger.info("OpenTelemetry 追踪已启用 (service={})", OTEL_SERVICE_NAME)
    return True


def get_tracer(name: str = "evoquant"):
    """获取一个 tracer 实例。未启用 OTel 时返回 NoOp tracer。"""
    try:
        from opentelemetry import trace
        return trace.get_tracer(name)
    except ImportError:
        return None
