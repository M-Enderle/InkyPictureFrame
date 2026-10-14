"""Switches: display on/off and automatic photo change."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import InkyConfigEntry, InkyCoordinator
from .entity import InkyEntity

# translation key -> field in the frame's settings
SWITCHES = {"display": "display_on", "slideshow": "slideshow"}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: InkyConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities(
        InkySwitch(entry.runtime_data, key, field) for key, field in SWITCHES.items()
    )


class InkySwitch(InkyEntity, SwitchEntity):
    def __init__(self, coordinator: InkyCoordinator, key: str, field: str) -> None:
        super().__init__(coordinator, key)
        self._field = field

    @property
    def is_on(self) -> bool:
        return bool(self.frame[self._field])

    async def _set(self, value: bool) -> None:
        await self.coordinator.async_send(
            self.coordinator.api.settings(**{self._field: value})
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set(False)
