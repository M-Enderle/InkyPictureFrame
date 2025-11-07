from __future__ import annotations

from immich import get_image_ids

from dotenv import load_dotenv
from inky.auto import auto

load_dotenv()
display = auto()

print(f"Detected Inky display: {display}")
print(get_image_ids())