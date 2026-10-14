"""Sensors: status, current photo details, album size, change timestamps."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import InkyConfigEntry
from .entity import InkyEntity

STATUSES = ["starting", "idle", "updating", "off", "error"]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: InkyConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    c = entry.runtime_data
    async_add_entities(
        [
            InkyStatusSensor(c, "status"),
            InkyCurrentPhotoSensor(c, "current_photo"),
            InkyAlbumCountSensor(c, "album_count"),
            InkyTimestampSensor(c, "last_change"),
            InkyTimestampSensor(c, "next_change"),
        ]
    )


class InkyStatusSensor(InkyEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = STATUSES
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self) -> str:
        return self.frame["status"]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"last_error": self.frame.get("last_error")}


class InkyCurrentPhotoSensor(InkyEntity, SensorEntity):
    @property
    def native_value(self) -> str | None:
        return (self.frame.get("current") or {}).get("filename")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        current = self.frame.get("current") or {}
        return {
            "album": self.frame.get("album_name"),
            "taken": current.get("taken"),
            "location": current.get("location"),
            "description": current.get("description"),
            "immich_url": current.get("url"),
            "asset_id": current.get("id"),
        }


class InkyAlbumCountSensor(InkyEntity, SensorEntity):
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self) -> int:
        return self.frame["album_count"]


class InkyTimestampSensor(InkyEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    @property
    def native_value(self) -> datetime | None:
        raw = self.frame.get(self._attr_translation_key)
        return dt_util.parse_datetime(raw) if raw else None
