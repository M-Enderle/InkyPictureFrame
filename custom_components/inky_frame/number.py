"""Number: interval between photo changes."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import InkyConfigEntry
from .entity import InkyEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: InkyConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([InkyIntervalNumber(entry.runtime_data, "interval")])


class InkyIntervalNumber(InkyEntity, NumberEntity):
    _attr_mode = NumberMode.BOX
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES

    @property
    def native_min_value(self) -> float:
        return self.frame["min_interval_min"]

    @property
    def native_max_value(self) -> float:
        return self.frame["max_interval_min"]

    @property
    def native_value(self) -> float:
        return self.frame["interval_min"]

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_send(
            self.coordinator.api.settings(interval_min=int(value))
        )
