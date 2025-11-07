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
import time
from pathlib import Path
from typing import Optional

from .immich-api import get_image_ids

from dotenv import load_dotenv
from inky.auto import auto

load_dotenv()
display = auto()

print(f"Detected Inky display: {display}")
print(get_image_ids())