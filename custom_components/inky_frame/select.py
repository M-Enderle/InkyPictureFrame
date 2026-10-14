"""Selects: orientation and Immich album."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
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
    async_add_entities(
        [InkyOrientationSelect(coordinator, "orientation"), InkyAlbumSelect(coordinator, "album")]
    )


class InkyOrientationSelect(InkyEntity, SelectEntity):
    _attr_options = ["landscape", "portrait"]

    @property
    def current_option(self) -> str:
        return self.frame["orientation"]

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_send(self.coordinator.api.settings(orientation=option))


class InkyAlbumSelect(InkyEntity, SelectEntity):
    def _by_name(self) -> dict[str, str]:
        """Album name -> id; disambiguate duplicate names with the id prefix."""
        result: dict[str, str] = {}
        for album in self.frame["albums"]:
            name = album["name"]
            if name in result:
                name = f"{name} ({album['id'][:4]})"
            result[name] = album["id"]
        return result

    @property
    def options(self) -> list[str]:
        return list(self._by_name())

    @property
    def current_option(self) -> str | None:
        for name, album_id in self._by_name().items():
            if album_id == self.frame["album_id"]:
                return name
        return None

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_send(
            self.coordinator.api.settings(album_id=self._by_name()[option])
        )
