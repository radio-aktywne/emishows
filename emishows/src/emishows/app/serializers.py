import json
from datetime import datetime
from json import JSONDecodeError
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.db import transaction
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from emishows.app.models import Event, Show
from emishows.events import CalendarError, calendars
from emishows.utils import parse_datetime_with_timezone


class ShowSerializer(serializers.ModelSerializer):
    class Meta:
        model = Show
        fields = "__all__"


class DateTimeField(serializers.DateTimeField):
    def to_internal_value(self, data):
        if not isinstance(data, str):
            raise ValidationError("Must be string.")
        try:
            return parse_datetime_with_timezone(data)
        except (ValueError, ZoneInfoNotFoundError) as e:
            raise ValidationError(
                f"Invalid datetime format. Example of valid one: '2000-01-01T20:00:00 Europe/Warsaw'"
            ) from e

    @staticmethod
    def _format(dt: datetime) -> str:
        return f"{dt.strftime('%Y-%m-%dT%H:%M:%S')} {dt.tzinfo}"

    def to_representation(self, value):
        if not isinstance(value, datetime):
            raise ValidationError("Value must be datetime.")
        if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
            raise ValidationError("Datetime must be timezone-aware.")
        if not isinstance(value.tzinfo, ZoneInfo):
            raise ValidationError("Timezone must be ZoneInfo.")
        return self._format(value)


class JSONField(serializers.Field):
    def to_internal_value(self, data):
        if data is None or data == "" or data == {}:
            return None
        try:
            if not isinstance(data, str):
                data = json.dumps(data)
            return json.loads(data)
        except JSONDecodeError as e:
            raise ValidationError("Invalid JSON data.") from e

    def to_representation(self, value):
        return value


class BaseEventParamsSerializer(serializers.Serializer):
    start = DateTimeField()
    end = DateTimeField()
    rules = JSONField(required=False, allow_null=True, default=None)


class EventParamsSerializer(BaseEventParamsSerializer):
    def _get_id(self):
        return self.context["id"]

    def to_representation(self, instance):
        try:
            event = calendars["emitimes"].get(self._get_id())
        except CalendarError as e:
            raise ValidationError(
                "Unable to retrieve event parameters."
            ) from e
        return {
            "start": self.fields["start"].to_representation(event.start),
            "end": self.fields["end"].to_representation(event.end),
            "rules": self.fields["rules"].to_representation(event.rules),
        }

    def update(self, instance, validated_data):
        try:
            calendars["emitimes"].update(self._get_id(), **validated_data)
        except CalendarError as e:
            raise ValidationError("Unable to save event parameters.") from e
        return instance

    def create(self, validated_data):
        try:
            calendars["emitimes"].add(
                uid=self._get_id(),
                start=validated_data["start"],
                end=validated_data["end"],
                rules=validated_data.get("rules"),
            )
        except CalendarError as e:
            raise ValidationError("Unable to save event parameters.") from e


class BaseEventSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(read_only=True)

    class Meta:
        model = Event
        fields = ["id", "show", "type"]

    def to_representation(self, instance):
        response = super().to_representation(instance)
        response["show"] = ShowSerializer(instance.show).data
        return response


class EventSerializer(BaseEventSerializer):
    params = EventParamsSerializer(allow_null=True)

    class Meta:
        model = Event
        fields = ["id", "show", "type", "params"]

    def _set_context(self, uid):
        self.fields["params"].context["id"] = uid

    @staticmethod
    def validate_params(value):
        if value is None:
            raise ValidationError("Params can't be null.")
        return value

    def to_representation(self, instance):
        self._set_context(instance.id)
        response = super().to_representation(instance)
        response["params"] = self.fields["params"].to_representation(None)
        return response

    @transaction.atomic
    def create(self, validated_data):
        if "id" not in validated_data:
            validated_data["id"] = uuid4()

        self._set_context(validated_data["id"])

        params = validated_data.pop("params", {})
        event = Event.objects.create(**validated_data)
        self.fields["params"].create(params)
        return event

    @transaction.atomic
    def update(self, instance, validated_data):
        uid = validated_data.get("id", self.instance.id)
        self._set_context(uid)

        new_params = validated_data.pop("params", {})
        old_params = self.fields["params"].to_representation(None)

        instance.id = uid
        instance.show = validated_data.get("show", instance.show)
        instance.type = validated_data.get("type", instance.type)
        instance.save()

        self.fields["params"].update(old_params, new_params)
        return instance
