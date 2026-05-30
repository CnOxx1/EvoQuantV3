from datetime import datetime, timedelta, timezone

from database.db_manager import DBManager
from data_layer.event_calendar_data.client import EventCalendarClient
from data_layer.event_calendar_data.models import (
    EventCalendarEvent,
    dump_json,
    utc_now_naive,
)
from data_layer.event_calendar_data.sources import load_event_calendar_sources


class EventCalendarCollector:
    """事件日历采集、标准化与落库。"""

    def __init__(self, client: EventCalendarClient, db: DBManager):
        self.client = client
        self.db = db

    @staticmethod
    def _normalize_filter(values: list[str] | None) -> set[str]:
        return {
            value.strip().lower()
            for value in (values or [])
            if value.strip()
        }

    def _select_sources(
        self,
        source_names: list[str] | None = None,
        event_types: list[str] | None = None,
    ):
        return load_event_calendar_sources(
            source_names=source_names,
            event_types=event_types,
        )

    @staticmethod
    def _parse_datetime(value) -> datetime:
        if isinstance(value, datetime):
            return value
        if not isinstance(value, str):
            raise ValueError("scheduled_at 必须是 ISO 时间字符串或 datetime")

        text = value.strip()
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        return datetime.fromisoformat(text)

    @staticmethod
    def _event_rank(event: EventCalendarEvent) -> tuple:
        status_rank = {
            "completed": 3,
            "canceled": 2,
            "updated": 1,
            "scheduled": 0,
        }
        return (
            event.collected_at,
            status_rank.get(event.status, -1),
            event.scheduled_at,
        )

    def _deduplicate_events(
        self,
        events: list[EventCalendarEvent],
    ) -> list[EventCalendarEvent]:
        deduped: dict[str, EventCalendarEvent] = {}
        for event in events:
            previous = deduped.get(event.event_key or "")
            if previous is None or self._event_rank(event) >= self._event_rank(previous):
                deduped[event.event_key or ""] = event
        return list(deduped.values())

    def _normalize_event(self, raw_event: dict, source) -> EventCalendarEvent:
        event_type = str(raw_event.get("event_type") or source.event_type).strip().lower()
        title = str(raw_event.get("title") or raw_event.get("name") or "").strip()
        if not title:
            raise ValueError("事件缺少 title")

        scheduled_at = self._parse_datetime(
            raw_event.get("scheduled_at")
            or raw_event.get("start_at")
            or raw_event.get("start_time")
            or raw_event.get("datetime")
        )

        raw_tags = raw_event.get("tags")
        if isinstance(raw_tags, list):
            event_tags = [str(item) for item in raw_tags]
        elif isinstance(raw_tags, str):
            event_tags = [item.strip() for item in raw_tags.split(",") if item.strip()]
        else:
            event_tags = []

        importance_score = raw_event.get("importance_score")
        return EventCalendarEvent(
            event_key=raw_event.get("event_key"),
            event_type=event_type,
            title=title,
            description=raw_event.get("description") or raw_event.get("summary"),
            symbol=str(raw_event.get("symbol") or source.default_symbol or "MARKET"),
            scheduled_at=scheduled_at,
            timezone=str(raw_event.get("timezone") or source.timezone or "UTC"),
            importance_score=None if importance_score is None else float(importance_score),
            source_name=source.name,
            status=str(raw_event.get("status") or "scheduled"),
            source_url=raw_event.get("source_url") or raw_event.get("url") or source.endpoint,
            external_id=raw_event.get("external_id") or raw_event.get("id") or raw_event.get("uid"),
            tags=[*source.tags, *event_tags],
            collected_at=utc_now_naive(),
            raw_payload_json=raw_event.get("raw_payload_json") or dump_json(raw_event),
        )

    def collect(
        self,
        lookahead_days: int | None = None,
        source_names: list[str] | None = None,
        event_types: list[str] | None = None,
        symbols: list[str] | None = None,
    ) -> list[EventCalendarEvent]:
        selected_sources = self._select_sources(
            source_names=source_names,
            event_types=event_types,
        )
        if not selected_sources:
            return []

        normalized_symbols = {
            value.strip().upper()
            for value in (symbols or [])
            if value.strip()
        }
        events: list[EventCalendarEvent] = []
        for source in selected_sources:
            events.extend(
                self.collect_source(
                    source=source,
                    lookahead_days=lookahead_days,
                    normalized_symbols=normalized_symbols,
                )
            )

        deduped = self._deduplicate_events(events)
        self.save_to_db(deduped)
        return deduped

    def collect_source(
        self,
        source,
        lookahead_days: int | None = None,
        normalized_symbols: set[str] | None = None,
    ) -> list[EventCalendarEvent]:
        lookahead = lookahead_days if lookahead_days is not None else 90
        now = datetime.now(timezone.utc)
        earliest_allowed = now - timedelta(days=7)
        latest_allowed = now + timedelta(days=lookahead)

        events: list[EventCalendarEvent] = []
        raw_events = self.client.fetch_events(source, lookahead_days=lookahead)
        for raw_event in raw_events:
            event = self._normalize_event(raw_event, source)
            scheduled_at_aware = event.scheduled_at.replace(tzinfo=timezone.utc)
            if scheduled_at_aware < earliest_allowed or scheduled_at_aware > latest_allowed:
                continue
            if normalized_symbols and event.symbol.upper() not in normalized_symbols:
                continue
            events.append(event)

        return self._deduplicate_events(events)

    def save_to_db(self, events: list[EventCalendarEvent]):
        events = self._deduplicate_events(events)
        if not events:
            return

        sql = """
            INSERT INTO event_calendar_events (
                event_key, event_type, title, description, symbol,
                scheduled_at, timezone, importance_score, source_name, status,
                source_url, external_id, tags, collected_at, raw_payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(event_key) DO UPDATE SET
                event_type=excluded.event_type,
                title=excluded.title,
                description=excluded.description,
                symbol=excluded.symbol,
                scheduled_at=excluded.scheduled_at,
                timezone=excluded.timezone,
                importance_score=excluded.importance_score,
                source_name=excluded.source_name,
                status=excluded.status,
                source_url=excluded.source_url,
                external_id=excluded.external_id,
                tags=excluded.tags,
                collected_at=excluded.collected_at,
                raw_payload_json=excluded.raw_payload_json,
                updated_at=CURRENT_TIMESTAMP
        """
        self.db.execute_many(sql, [event.db_tuple() for event in events])
        self.db.commit()
