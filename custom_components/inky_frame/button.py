"""Buttons: next / previous photo, reload album."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import InkyConfigEntry, InkyCoordinator
from .entity import InkyEntity

BUTTONS = {
    "next_photo": "next",
    "previous_photo": "previous",
    "reload_album": "reload",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: InkyConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities(
        InkyButton(entry.runtime_data, key, command) for key, command in BUTTONS.items()
    )


class InkyButton(InkyEntity, ButtonEntity):
    def __init__(self, coordinator: InkyCoordinator, key: str, command: str) -> None:
        super().__init__(coordinator, key)
        self._command = command
        if command == "reload":
            self._attr_entity_category = EntityCategory.CONFIG

    async def async_press(self) -> None:
        await self.coordinator.async_send(self.coordinator.api.command(self._command))
