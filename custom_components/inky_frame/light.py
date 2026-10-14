"""Light: the dimmable LED connected to the Pi (only if configured)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.light import ATTR_BRIGHTNESS, ColorMode, LightEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import InkyConfigEntry
from .entity import InkyEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: InkyConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    if coordinator.data["led"]["available"]:
        async_add_entities([InkyLed(coordinator, "led")])


class InkyLed(InkyEntity, LightEntity):
    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}

    @property
    def is_on(self) -> bool:
        return self.frame["led"]["on"]

    @property
    def brightness(self) -> int:
        return self.frame["led"]["brightness"]

    async def async_turn_on(self, **kwargs: Any) -> None:
        values: dict[str, Any] = {"on": True}
        if ATTR_BRIGHTNESS in kwargs:
            values["brightness"] = kwargs[ATTR_BRIGHTNESS]
        await self.coordinator.async_send(self.coordinator.api.led(**values))

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_send(self.coordinator.api.led(on=False))
