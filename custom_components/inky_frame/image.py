"""Image: live preview of what the frame currently shows."""

from __future__ import annotations

from homeassistant.components.image import ImageEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .api import InkyApiError
from .coordinator import InkyConfigEntry, InkyCoordinator
from .entity import InkyEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: InkyConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([InkyPhoto(hass, entry.runtime_data, "photo")])


class InkyPhoto(InkyEntity, ImageEntity):
    _attr_content_type = "image/jpeg"

    def __init__(self, hass: HomeAssistant, coordinator: InkyCoordinator, key: str) -> None:
        InkyEntity.__init__(self, coordinator, key)
        ImageEntity.__init__(self, hass)
        self._attr_image_last_updated = self._last_change()

    def _last_change(self):
        raw = self.frame.get("last_change")
        return dt_util.parse_datetime(raw) if raw else None

    def _handle_coordinator_update(self) -> None:
        self._attr_image_last_updated = self._last_change()
        super()._handle_coordinator_update()

    async def async_image(self) -> bytes | None:
        try:
            return await self.coordinator.api.image()
        except InkyApiError:
            return None
