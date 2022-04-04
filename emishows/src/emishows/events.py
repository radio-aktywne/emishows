from datetime import datetime
from typing import Any, Dict, Iterator, List, Optional
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import caldav
import httpx
import icalendar
import recurring_ical_events
from caldav import DAVClient
from caldav.lib.error import DAVError
from pydantic import BaseModel, ValidationError

EVENT_TO_ICALENDAR_NAME_MAPPING = {
    "uid": "uid",
    "start": "dtstart",
    "end": "dtend",
    "rules": "rrule",
}


class CalendarError(RuntimeError):
    pass


class Event(BaseModel):
    uid: UUID
    start: datetime
    end: datetime
    rules: Optional[Dict[str, Any]] = None


class Calendar:
    def __init__(
        self,
        url: str,
        name: str,
        user: Optional[str] = None,
        password: Optional[str] = None,
    ) -> None:
        self.url = url
        self.name = name
        self.user = user
        self.password = password
        self.calendar = (
            DAVClient(url=url, username=user, password=password)
            .principal()
            .calendar(cal_id=name)
        )

    @staticmethod
    def _retrieve_vevent(calendar: icalendar.Calendar) -> icalendar.Event:
        return calendar.walk("vevent")[0]

    @staticmethod
    def _patch_incoming_datetime(dt: datetime) -> datetime:
        class PatchedZoneInfo(ZoneInfo):
            @property
            def zone(self) -> str:
                return str(self)

        if isinstance(dt.tzinfo, ZoneInfo):
            dt = dt.replace(tzinfo=PatchedZoneInfo(dt.tzinfo.key))
        return dt

    @staticmethod
    def _patch_outgoing_datetime(
        dt: datetime, event: icalendar.Event, key: str
    ) -> datetime:
        tzid = event.get(key).params.get("TZID", "Etc/UTC")
        try:
            return dt.replace(tzinfo=ZoneInfo(tzid))
        except ZoneInfoNotFoundError as e:
            raise CalendarError("Invalid timezone.") from e

    @staticmethod
    def _map_vevent(event: icalendar.Event) -> Event:
        params = {}
        for event_key, ical_key in EVENT_TO_ICALENDAR_NAME_MAPPING.items():
            decoded = event.decoded(ical_key, None)
            if isinstance(decoded, datetime):
                decoded = Calendar._patch_outgoing_datetime(
                    decoded, event, ical_key
                )
            params[event_key] = decoded
        try:
            return Event(**params)
        except ValidationError as e:
            raise CalendarError("Invalid event data.") from e

    @staticmethod
    def _map_event(event: caldav.CalendarObjectResource) -> Event:
        event = Calendar._retrieve_vevent(event.icalendar_instance)
        return Calendar._map_vevent(event)

    @staticmethod
    def _update_vevent(
        vevent: icalendar.Event, event: Event
    ) -> icalendar.Event:
        tmp_event = icalendar.Event()
        for k, v in event.dict().items():
            if v is not None:
                ical_key = EVENT_TO_ICALENDAR_NAME_MAPPING[k]
                if isinstance(v, datetime):
                    v = Calendar._patch_incoming_datetime(v)
                tmp_event.add(ical_key, v)
                vevent[ical_key] = tmp_event[ical_key]
        return vevent

    @staticmethod
    def _update_calendar(
        calendar: icalendar.Calendar, **kwargs
    ) -> icalendar.Calendar:
        vevent = Calendar._retrieve_vevent(calendar)
        try:
            event = Calendar._map_vevent(vevent).copy(update=kwargs)
        except ValidationError as e:
            raise CalendarError("Invalid event data.") from e
        Calendar._update_vevent(vevent, event)
        return calendar

    @staticmethod
    def _new_calendar(**kwargs) -> icalendar.Calendar:
        calendar = icalendar.Calendar()
        vevent = icalendar.Event()
        calendar.add_component(vevent)
        try:
            event = Event(**kwargs)
        except ValidationError as e:
            raise CalendarError("Invalid event data.") from e
        Calendar._update_vevent(vevent, event)
        return calendar

    @staticmethod
    def _expand_events(
        events: List[caldav.CalendarObjectResource],
        from_date: datetime,
        to_date: datetime,
    ) -> List[Event]:
        out = []
        for event in events:
            calendar = recurring_ical_events.of(event.icalendar_instance)
            for vevent in calendar.between(from_date, to_date):
                out.append(Calendar._map_vevent(vevent))
        return out

    def add(self, **kwargs) -> Event:
        calendar = self._new_calendar(**kwargs)
        ics = calendar.to_ical()
        try:
            event = self.calendar.save_event(ics)
        except DAVError as e:
            raise CalendarError("Can't add event.") from e
        return self._map_event(event)

    def update(self, uid: UUID, **kwargs) -> Event:
        try:
            event = self.calendar.event_by_uid(str(uid))
        except DAVError as e:
            raise CalendarError("Can't retrieve event.") from e
        calendar = self._update_calendar(event.icalendar_instance, **kwargs)
        event.icalendar_instance = calendar
        try:
            event.save()
        except DAVError as e:
            raise CalendarError("Can't update event.") from e
        return self._map_event(event)

    def get(self, uid: UUID) -> Event:
        try:
            event = self.calendar.event_by_uid(str(uid))
        except DAVError as e:
            raise CalendarError("Can't retrieve event.") from e
        return self._map_event(event)

    def delete(self, uid: UUID) -> None:
        try:
            event = self.calendar.event_by_uid(str(uid))
        except DAVError as e:
            raise CalendarError("Can't retrieve event.") from e
        event.delete()

    def search(
        self, from_date: datetime, to_date: datetime, expand: bool = True
    ) -> List[Event]:
        try:
            events = self.calendar.date_search(from_date, to_date)
        except DAVError as e:
            raise CalendarError("Can't retrieve events.") from e
        if expand:
            return self._expand_events(events, from_date, to_date)
        return [self._map_event(event) for event in events]

    def ics(self) -> Iterator[str]:
        with httpx.stream(
            "GET", self.calendar.canonical_url, auth=(self.user, self.password)
        ) as r:
            yield from r.iter_text()


calendars: Dict[str, Calendar] = {}
