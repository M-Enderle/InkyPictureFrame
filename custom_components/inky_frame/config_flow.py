"""Config flow: manual entry, mDNS discovery and re-authentication."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from .api import InkyApiError, InkyAuthError, InkyConnectionError, InkyFrameApi
from .const import CONF_API_TOKEN, DEFAULT_PORT, DOMAIN


class InkyFrameConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._host: str | None = None
        self._port: int = DEFAULT_PORT
        self._name: str = "Inky Frame"

    async def _validate(self, host: str, port: int, token: str) -> dict[str, Any]:
        api = InkyFrameApi(async_get_clientsession(self.hass), host, port, token)
        info = await api.health()
        if info.get("app") != "inky-frame":
            raise InkyApiError("not an inky frame")
        await api.status()  # raises InkyAuthError on a bad token
        return info

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                info = await self._validate(
                    user_input[CONF_HOST], user_input[CONF_PORT], user_input[CONF_API_TOKEN]
                )
            except InkyAuthError:
                errors["base"] = "invalid_auth"
            except InkyConnectionError:
                errors["base"] = "cannot_connect"
            except InkyApiError:
                errors["base"] = "not_inky_frame"
            else:
                await self.async_set_unique_id(info["id"])
                self._abort_if_unique_id_configured(
                    updates={
                        CONF_HOST: user_input[CONF_HOST],
                        CONF_PORT: user_input[CONF_PORT],
                    }
                )
                return self.async_create_entry(title=info["name"], data=user_input)
        defaults = user_input or {}
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, "")): str,
                    vol.Required(
                        CONF_PORT, default=defaults.get(CONF_PORT, DEFAULT_PORT)
                    ): int,
                    vol.Required(CONF_API_TOKEN): str,
                }
            ),
            errors=errors,
        )

    async def async_step_zeroconf(
        self, discovery_info: ZeroconfServiceInfo
    ) -> ConfigFlowResult:
        device_id = discovery_info.properties.get("id")
        if not device_id:
            return self.async_abort(reason="not_inky_frame")
        await self.async_set_unique_id(device_id)
        self._abort_if_unique_id_configured(
            updates={CONF_HOST: discovery_info.host, CONF_PORT: discovery_info.port}
        )
        self._host = discovery_info.host
        self._port = discovery_info.port or DEFAULT_PORT
        self._name = discovery_info.properties.get("name", self._name)
        self.context["title_placeholders"] = {"name": self._name}
        return await self.async_step_zeroconf_confirm()

    async def async_step_zeroconf_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        assert self._host is not None
        if user_input is not None:
            try:
                info = await self._validate(self._host, self._port, user_input[CONF_API_TOKEN])
            except InkyAuthError:
                errors["base"] = "invalid_auth"
            except InkyApiError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(
                    title=info["name"],
                    data={
                        CONF_HOST: self._host,
                        CONF_PORT: self._port,
                        CONF_API_TOKEN: user_input[CONF_API_TOKEN],
                    },
                )
        return self.async_show_form(
            step_id="zeroconf_confirm",
            data_schema=vol.Schema({vol.Required(CONF_API_TOKEN): str}),
            description_placeholders={"name": self._name, "host": self._host},
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            try:
                await self._validate(
                    entry.data[CONF_HOST], entry.data[CONF_PORT], user_input[CONF_API_TOKEN]
                )
            except InkyAuthError:
                errors["base"] = "invalid_auth"
            except InkyApiError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_API_TOKEN: user_input[CONF_API_TOKEN]}
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_API_TOKEN): str}),
            errors=errors,
        )
