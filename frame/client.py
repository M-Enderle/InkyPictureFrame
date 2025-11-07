"""Simple Inky image cycler.

Reads configuration from `.env` (or environment variables):
  IMAGE_FOLDER  - folder containing images (default: ./images)
  INTERVAL      - seconds between images (default: 30)
  ASK_USER      - whether to prompt for Inky selection (default: True)
  DELETE_AFTER_DISPLAY - true/false whether to delete displayed images (default: True)

The script picks a random image from IMAGE_FOLDER, displays it on the attached
Inky device using `inky.auto.auto`, deletes the file after successful display,
and repeats every INTERVAL seconds. Keeps the code intentionally small and
focused on the Inky path.
"""

from __future__ import annotations

import logging
import os
import random
import sys
import time
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from PIL import Image

from inky.auto import auto

load_dotenv()

LOGGER = logging.getLogger("frame.client")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def _get_env(name: str, default: Optional[str] = None) -> Optional[str]:
    return os.environ.get(name, default)


def _bool_env(name: str, default: bool) -> bool:
    v = _get_env(name)
    if v is None:
        return default
    return v.lower() in ("1", "true", "yes", "y")


def main():
    # Config
    folder = Path(_get_env("IMAGE_FOLDER", "./images")).expanduser()
    interval = float(_get_env("INTERVAL", "30"))
    delete_after = _bool_env("DELETE_AFTER_DISPLAY", True)

    # Prepare folder
    folder.mkdir(parents=True, exist_ok=True)

    supported = (".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp")

    LOGGER.info("Starting Inky cycler: folder=%s interval=%s delete_after=%s", folder, interval, delete_after)

    while True:
        try:
            files = [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in supported]
            if not files:
                LOGGER.warning("No images found in %s — sleeping %s seconds", folder, interval)
                time.sleep(interval)
                continue

            path = random.choice(files)
            LOGGER.info("Displaying %s", path)

            # Open and load image fully before deleting the file
            img = Image.open(path)
            img.load()

            try:
                # Send to Inky
                inky.set_image(img)
                inky.show()
                LOGGER.info("Displayed %s on Inky", path)
            except Exception:
                LOGGER.exception("Failed to display on Inky: %s", path)
                # Do not delete on failure
                time.sleep(interval)
                continue

            if delete_after:
                try:
                    path.unlink()
                    LOGGER.info("Deleted %s after display", path)
                except Exception:
                    LOGGER.exception("Failed to delete %s after display", path)

        except Exception:
            LOGGER.exception("Unexpected error in main loop")

        time.sleep(interval)


if __name__ == "__main__":
    main()