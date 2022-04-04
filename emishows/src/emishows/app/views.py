from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfoNotFoundError

from django.db import transaction
from django.http import StreamingHttpResponse
from rest_framework import views, viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from emishows.app.models import Event, Show
from emishows.app.serializers import (
    BaseEventParamsSerializer,
    BaseEventSerializer,
    EventSerializer,
    ShowSerializer,
)
from emishows.events import CalendarError, calendars
from emishows.utils import (
    parse_datetime_with_timezone,
    utcnow,
)


class ShowViewSet(viewsets.ModelViewSet):
    queryset = Show.objects.all()
    serializer_class = ShowSerializer


class EventViewSet(viewsets.ModelViewSet):
    queryset = Event.objects.all()
    serializer_class = EventSerializer
    filterset_fields = ["show", "type"]

    @transaction.atomic
    def perform_destroy(self, instance: Event):
        uid = instance.id
        super().perform_destroy(instance)
        try:
            calendars["emitimes"].delete(uid)
        except CalendarError as e:
            raise ValidationError("Unable to delete event params.") from e


class TimetableViewSet(viewsets.ViewSet):
    def list(self, request):
        from_date = self.request.query_params.get("from")
        to_date = self.request.query_params.get("to")

        now = utcnow()

        try:
            from_date = self.parse_datetime(from_date, now)
        except (ValueError, ZoneInfoNotFoundError) as e:
            raise ValidationError("from_date is not a valid datetime.") from e

        try:
            to_date = self.parse_datetime(to_date, now)
        except (ValueError, ZoneInfoNotFoundError) as e:
            raise ValidationError("to_date is not a valid datetime.") from e

        calendar_events = calendars["emitimes"].search(from_date, to_date)
        ids = set(event.uid for event in calendar_events)

        queryset = Event.objects.filter(id__in=ids)
        serialized_events_map = {
            event.id: BaseEventSerializer(event).data for event in queryset
        }

        out = []
        for event in calendar_events:
            data = {
                **serialized_events_map[event.uid],
                "params": BaseEventParamsSerializer(event).data,
            }
            out.append(data)

        return Response(out)

    @staticmethod
    def parse_datetime(
        dt: Optional[str], default: Optional[datetime] = None
    ) -> datetime:
        if dt is None:
            return default or utcnow()
        return parse_datetime_with_timezone(dt)


class ICSView(views.APIView):
    def get(self, request):
        calendar = calendars["emitimes"]
        filename = f"{calendar.name}.ics"
        headers = {
            "Content-Type": "text/calendar; charset=utf-8",
            "Content-Disposition": f'attachment; filename="{filename}"',
        }
        return StreamingHttpResponse(calendar.ics(), headers=headers)
