"""HTTP API consumed by the Home Assistant integration."""

from __future__ import annotations

import asyncio
import secrets
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from .client import Controller
from .config import MAX_INTERVAL_MIN, MIN_INTERVAL_MIN, VERSION, Settings
from .discovery import Announcer

COMMANDS = {"next", "previous", "reload", "clear"}


class SettingsBody(BaseModel):
    interval_min: int | None = Field(None, ge=MIN_INTERVAL_MIN, le=MAX_INTERVAL_MIN)
    orientation: Literal["landscape", "portrait"] | None = None
    album_id: str | None = Field(None, min_length=1)
    display_on: bool | None = None
    slideshow: bool | None = None


class LedBody(BaseModel):
    on: bool | None = None
    brightness: int | None = Field(None, ge=1, le=255)


def create_app(settings: Settings, controller: Controller) -> FastAPI:
    announcer = Announcer(
        settings.device_id, settings.device_name, settings.api_port, VERSION
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        controller.start()
        await asyncio.get_running_loop().run_in_executor(None, announcer.register)
        yield
        await asyncio.get_running_loop().run_in_executor(None, announcer.close)
        controller.stop()

    app = FastAPI(title="Inky Frame", version=VERSION, lifespan=lifespan)
    bearer = HTTPBearer(auto_error=False)

    def auth(creds: HTTPAuthorizationCredentials | None = Depends(bearer)) -> None:
        if creds is None or not secrets.compare_digest(
            creds.credentials.encode(), settings.api_token.encode()
        ):
            raise HTTPException(401, "Invalid token")

    @app.get("/api/v1/health")
    def health() -> dict:
        """Unauthenticated: lets the HA config flow identify the device."""
        return {
            "app": "inky-frame",
            "id": settings.device_id,
            "name": settings.device_name,
            "version": VERSION,
        }

    @app.get("/api/v1/status", dependencies=[Depends(auth)])
    def status() -> dict:
        return controller.snapshot()

    @app.get("/api/v1/image", dependencies=[Depends(auth)])
    def image(request: Request) -> Response:
        preview = controller.preview()
        if preview is None:
            raise HTTPException(404, "No image yet")
        data, etag = preview
        if request.headers.get("if-none-match") == f'"{etag}"':
            return Response(status_code=304)
        return Response(
            data, media_type="image/jpeg", headers={"ETag": f'"{etag}"', "Cache-Control": "no-cache"}
        )

    @app.post("/api/v1/command/{name}", status_code=202, dependencies=[Depends(auth)])
    def command(name: str) -> dict:
        if name not in COMMANDS:
            raise HTTPException(404, f"Unknown command {name}")
        controller.submit(name)
        return {"accepted": name}

    @app.post("/api/v1/settings", status_code=202, dependencies=[Depends(auth)])
    def update_settings(body: SettingsBody) -> dict:
        changes = body.model_dump(exclude_none=True)
        if changes:
            controller.submit("settings", changes)
        return {"accepted": changes}

    @app.post("/api/v1/led", dependencies=[Depends(auth)])
    def led(body: LedBody) -> dict:
        if not controller.led.available:
            raise HTTPException(409, "No LED configured (LED_GPIO)")
        controller.set_led(body.on, body.brightness)
        return controller.snapshot()["led"]

    return app
