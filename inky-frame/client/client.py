"""Polling client for Inky Frame.

This client polls the web UI endpoint for the current frame JSON every N
seconds (configurable) and displays the returned image on an attached Inky
display using the sample usage pattern provided by the user.

Behavior and assumptions:
- By default the client GETs /api/frame/current on the server and expects the
  JSON FramePayload described in `webui.app.FramePayload`.
- The polling interval is determined in this order:
  1. CLI `--interval` value if provided
  2. The server-sent `settings.change_interval` field in the frame payload
  3. Local config default (60s)
- CLI options allow host/port override and a one-shot `--once` mode for testing.
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import logging
import sys
import time
import urllib.request
from typing import Any, Dict, Optional

from PIL import Image

from inky.auto import auto

from .config import load as load_config


logger = logging.getLogger("inky_client")


def fetch_frame(url: str, timeout: int = 10) -> Dict[str, Any]:
    req = urllib.request.Request(url, method="GET", headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        if resp.status != 200:
            raise RuntimeError(f"Unexpected status: {resp.status}")
        raw = resp.read()
    return json.loads(raw.decode("utf-8"))


def render_payload_to_image(payload: Dict[str, Any]):
    b64 = payload.get("image_base64")
    if not b64:
        raise ValueError("frame payload missing image_base64")
    data = base64.b64decode(b64)
    return Image.open(io.BytesIO(data))


def main(argv: Optional[list[str]] = None) -> int:
    cfg = load_config()

    parser = argparse.ArgumentParser(description="Inky Frame polling client")
    parser.add_argument("--host", default=cfg.host, help="Server host")
    parser.add_argument("--port", type=int, default=cfg.port, help="Server port")
    parser.add_argument("--interval", "-i", type=int, default=None, help="Polling interval in seconds (overrides server/config)")
    parser.add_argument("--saturation", "-s", type=float, default=None, help="Override saturation when setting image on display")
    parser.add_argument("--once", action="store_true", help="Fetch one frame and exit")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    base_url = f"http://{args.host}:{args.port}"
    frame_url = f"{base_url}/api/frame/current"

    # initialize Inky display (asks user to select display if multiple)
    inky = auto(ask_user=True, verbose=args.verbose)
    logger.info("Using Inky display: %s, resolution=%s", type(inky).__name__, inky.resolution)

    try:
        while True:
            try:
                payload = fetch_frame(frame_url)
            except KeyboardInterrupt:
                raise
            except Exception:
                logger.exception("Failed to fetch frame; retrying in 5s")
                if args.once:
                    return 2
                time.sleep(5)
                continue

            try:
                img = render_payload_to_image(payload)
            except Exception:
                logger.exception("Failed to decode image from payload")
                if args.once:
                    return 3
                time.sleep(5)
                continue

            # prepare image for display
            try:
                resized = img.resize(inky.resolution)
            except Exception:
                logger.exception("Failed resizing image; using original")
                resized = img

            # choose saturation: CLI override > payload.settings.saturation > default 0.5
            sat = args.saturation
            if sat is None:
                settings = payload.get("settings") or {}
                sat = settings.get("saturation") if isinstance(settings, dict) else None
            if sat is None:
                sat = 0.5

            try:
                # sample code showed set_image may raise TypeError on some drivers
                inky.set_image(resized, saturation=sat)
            except TypeError:
                inky.set_image(resized)
            except Exception:
                logger.exception("Failed to set image on Inky display")

            try:
                inky.show()
            except Exception:
                logger.exception("Failed to show image on Inky display")

            # resolve next interval
            if args.interval is not None:
                next_interval = args.interval
            else:
                settings = payload.get("settings") or {}
                next_interval = settings.get("change_interval") if isinstance(settings, dict) else None
                if not isinstance(next_interval, int):
                    next_interval = cfg.poll_interval

            logger.info("Sleeping for %d seconds", next_interval)

            if args.once:
                return 0

            try:
                time.sleep(max(1, int(next_interval)))
            except KeyboardInterrupt:
                return 0

    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
