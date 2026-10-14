"""Data coordinator polling the frame."""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import InkyApiError, InkyAuthError, InkyFrameApi
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

SLOW = timedelta(seconds=30)
FAST = timedelta(seconds=3)  # while the e-ink panel is redrawing (~30 s)
FAST_WINDOW = 60.0

type InkyConfigEntry = ConfigEntry[InkyCoordinator]


class InkyCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    config_entry: InkyConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: InkyConfigEntry, api: InkyFrameApi
    ) -> None:
        super().__init__(
            hass, _LOGGER, config_entry=entry, name=DOMAIN, update_interval=SLOW
        )
        self.api = api
        self.device_id: str = entry.unique_id or entry.entry_id
        self.device_info = DeviceInfo(identifiers={(DOMAIN, self.device_id)})
        self._fast_until = 0.0

    def build_device_info(self) -> None:
        data = self.data
        self.device_info = DeviceInfo(
            identifiers={(DOMAIN, self.device_id)},
            name=data["name"],
            manufacturer="Pimoroni",
            model=data["model"],
            sw_version=data["version"],
            configuration_url=f"http://{self.api.host}:{self.api.port}/docs",
        )

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            data = await self.api.status()
        except InkyAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except InkyApiError as err:
            raise UpdateFailed(str(err)) from err
        busy = data["status"] == "updating" or time.monotonic() < self._fast_until
        self.update_interval = FAST if busy else SLOW
        return data

    async def async_send(self, call: Awaitable[None]) -> None:
        """Run an API call, then poll quickly until the frame has settled."""
        try:
            await call
        except InkyApiError as err:
            raise HomeAssistantError(f"Inky Frame: {err}") from err
        self._fast_until = time.monotonic() + FAST_WINDOW
        self.update_interval = FAST
        await self.async_request_refresh()
