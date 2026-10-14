"""Environment-driven configuration for the frame."""

from __future__ import annotations

import os
import re
import secrets
import socket
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

VERSION = "0.2.0"
ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / "frame" / ".env")

# Pimoroni recommends not refreshing Inky Impression panels more often than
# every few minutes; constantly redrawing also wears the e-ink display.
MIN_INTERVAL_MIN = 3
MAX_INTERVAL_MIN = 1440


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "") or default)
    except ValueError:
        return default


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_") or "inky_frame"


@dataclass(frozen=True)
class Settings:
    immich_url: str
    immich_key: str
    album_id: str
    orientation: str
    interval_min: int
    api_host: str
    api_port: int
    api_token: str
    device_id: str
    device_name: str
    led_gpio: int | None
    mock_display: bool
    data_dir: Path
    images_dir: Path
    logs_dir: Path

    @classmethod
    def load(cls) -> "Settings":
        data_dir = ROOT / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        orientation = os.getenv("ORIENTATION", "landscape").lower()
        led = os.getenv("LED_GPIO", "").strip()
        hostname = socket.gethostname()
        return cls(
            immich_url=os.getenv("IMMICH_BASE_URL", "").rstrip("/"),
            immich_key=os.getenv("IMMICH_API_KEY", ""),
            album_id=os.getenv("ALBUM_ID", ""),
            orientation="portrait" if orientation == "portrait" else "landscape",
            interval_min=min(
                max(_int("INTERVAL_MINUTES", 15), MIN_INTERVAL_MIN), MAX_INTERVAL_MIN
            ),
            api_host=os.getenv("API_HOST", "0.0.0.0"),
            api_port=_int("API_PORT", 8765),
            api_token=os.getenv("FRAME_API_TOKEN", "") or _load_token(data_dir),
            device_id=_slug(os.getenv("DEVICE_ID", "") or hostname),
            device_name=os.getenv("DEVICE_NAME", "") or "Inky Frame",
            led_gpio=int(led) if led.isdigit() else None,
            mock_display=os.getenv("MOCK_DISPLAY", "") == "1",
            data_dir=data_dir,
            images_dir=ROOT / "images",
            logs_dir=ROOT / "logs",
        )


def _load_token(data_dir: Path) -> str:
    """Return the persisted API token, generating one on first start."""
    path = data_dir / "api_token"
    if path.exists():
        token = path.read_text().strip()
        if token:
            return token
    token = secrets.token_urlsafe(24)
    path.write_text(token + "\n")
    path.chmod(0o600)
    return token
