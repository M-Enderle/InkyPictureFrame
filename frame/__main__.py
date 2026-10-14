"""Entrypoint: `python -m frame` starts the slideshow and the Home Assistant API."""

from __future__ import annotations

import logging
import sys

import uvicorn

from .api import create_app
from .client import Controller
from .config import Settings
from .display import create_display
from .immich import ImmichClient, ImmichError
from .led import Led
from .logs_setup import setup_logging

log = logging.getLogger("frame")


def main() -> None:
    settings = Settings.load()
    if "token" in sys.argv[1:]:
        print(settings.api_token)
        return
    setup_logging(settings.logs_dir)
    try:
        immich = ImmichClient(settings.immich_url, settings.immich_key)
    except ImmichError as err:
        log.error("%s — the frame starts, but cannot fetch photos", err)
        immich = None
    controller = Controller(
        settings,
        create_display(settings.mock_display, settings.data_dir),
        Led(settings.led_gpio),
        immich,
    )
    log.info("Frame API on %s:%d (token: `python -m frame token`)", settings.api_host, settings.api_port)
    uvicorn.run(
        create_app(settings, controller),
        host=settings.api_host,
        port=settings.api_port,
        log_level="warning",
    )


if __name__ == "__main__":
    main()
