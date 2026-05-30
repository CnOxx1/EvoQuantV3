import json

from loguru import logger

from config.settings import EVENT_CALENDAR_CONFIG
from data_layer.event_calendar_data.models import EventCalendarSource


def _normalize_filter(values: list[str] | None) -> set[str]:
    return {
        value.strip().lower()
        for value in (values or [])
        if value.strip()
    }


DEFAULT_EVENT_CALENDAR_SOURCES = [
    EventCalendarSource(
        name="Macro Calendar API",
        event_type="macro",
        endpoint=EVENT_CALENDAR_CONFIG["macro_source_url"] or None,
        description="宏观事件日历，建议输出 CPI / FOMC / 非农等未来时点。",
        tags=["macro", "calendar"],
    ),
    EventCalendarSource(
        name="ETF Calendar API",
        event_type="etf",
        endpoint=EVENT_CALENDAR_CONFIG["etf_source_url"] or None,
        description="ETF 申请、审议、审批、延期等节点日历。",
        tags=["etf", "regulation", "calendar"],
    ),
    EventCalendarSource(
        name="Token Unlock Calendar API",
        event_type="unlock",
        endpoint=EVENT_CALENDAR_CONFIG["unlock_source_url"] or None,
        description="项目解锁和大额线性释放事件日历。",
        tags=["tokenomics", "unlock", "calendar"],
    ),
    EventCalendarSource(
        name="Project Upgrade Calendar API",
        event_type="upgrade",
        endpoint=EVENT_CALENDAR_CONFIG["upgrade_source_url"] or None,
        description="主网升级、硬分叉、治理执行等项目节点日历。",
        tags=["upgrade", "governance", "calendar"],
    ),
]


def _load_extra_sources() -> list[EventCalendarSource]:
    raw_value = EVENT_CALENDAR_CONFIG.get("extra_sources_json", "").strip()
    if not raw_value:
        return []

    try:
        payload = json.loads(raw_value)
    except json.JSONDecodeError as exc:
        logger.error(f"解析 EVENT_CALENDAR_EXTRA_SOURCES_JSON 失败: {exc}")
        return []

    if not isinstance(payload, list):
        logger.error("EVENT_CALENDAR_EXTRA_SOURCES_JSON 必须是 JSON 数组")
        return []

    sources: list[EventCalendarSource] = []
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            logger.warning(f"跳过非法事件源配置 #{index}: 不是对象")
            continue
        try:
            sources.append(EventCalendarSource(**item))
        except Exception as exc:
            logger.warning(f"跳过非法事件源配置 #{index}: {exc}")
    return sources


def load_event_calendar_sources(
    source_names: list[str] | None = None,
    event_types: list[str] | None = None,
    enabled_only: bool = True,
) -> list[EventCalendarSource]:
    normalized_names = _normalize_filter(source_names)
    normalized_types = _normalize_filter(event_types)

    sources = [*DEFAULT_EVENT_CALENDAR_SOURCES, *_load_extra_sources()]
    selected: list[EventCalendarSource] = []
    for source in sources:
        if enabled_only and not source.enabled:
            continue
        if normalized_names and source.name.lower() not in normalized_names:
            continue
        if normalized_types and source.event_type.lower() not in normalized_types:
            continue
        selected.append(source)
    return selected
