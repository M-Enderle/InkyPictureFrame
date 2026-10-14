"""Async client for the Inky Frame HTTP API."""

from __future__ import annotations

from typing import Any

import aiohttp


class InkyApiError(Exception):
    """Base error for the frame API."""


class InkyConnectionError(InkyApiError):
    """The frame could not be reached."""


class InkyAuthError(InkyApiError):
    """The API token was rejected."""


class InkyFrameApi:
    def __init__(
        self, session: aiohttp.ClientSession, host: str, port: int, token: str
    ) -> None:
        self._session = session
        self._base = f"http://{host}:{port}/api/v1"
        self._token = token
        self.host = host
        self.port = port

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        auth: bool = True,
        raw: bool = False,
    ) -> Any:
        headers = {"Authorization": f"Bearer {self._token}"} if auth else {}
        try:
            async with self._session.request(
                method,
                f"{self._base}{path}",
                json=json,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status == 401:
                    raise InkyAuthError("Invalid API token")
                if resp.status == 404 and raw:
                    return None
                if resp.status >= 400:
                    raise InkyApiError(f"{path}: HTTP {resp.status} {await resp.text()}")
                return await resp.read() if raw else await resp.json()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise InkyConnectionError(f"Cannot reach frame: {err}") from err

    async def health(self) -> dict[str, Any]:
        return await self._request("GET", "/health", auth=False)

    async def status(self) -> dict[str, Any]:
        return await self._request("GET", "/status")

    async def image(self) -> bytes | None:
        return await self._request("GET", "/image", raw=True)

    async def command(self, name: str) -> None:
        await self._request("POST", f"/command/{name}")

    async def settings(self, **values: Any) -> None:
        await self._request("POST", "/settings", json=values)

    async def led(self, **values: Any) -> None:
        await self._request("POST", "/led", json=values)
