"""Image preparation for the e-ink panel."""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageOps

from .immich import classify


def prepare(
    path: Path, resolution: tuple[int, int], orientation: str
) -> tuple[Image.Image, Image.Image]:
    """Return (preview, device_image).

    The preview is what a viewer sees on the wall; the device image is rotated
    when the frame hangs in portrait mode so the panel's native raster matches.
    """
    target = resolution
    if orientation == "portrait":
        target = (resolution[1], resolution[0])
    with Image.open(path) as img:
        img = ImageOps.exif_transpose(img).convert("RGB")
        preview = ImageOps.fit(img, target, Image.Resampling.LANCZOS)
    device = preview.rotate(90, expand=True) if orientation == "portrait" else preview
    return preview, device


def blank(resolution: tuple[int, int]) -> Image.Image:
    return Image.new("RGB", resolution, (255, 255, 255))


def to_jpeg(image: Image.Image, max_side: int = 960) -> bytes:
    thumb = image.copy()
    thumb.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    thumb.save(buf, "JPEG", quality=85)
    return buf.getvalue()


def fits(path: Path, orientation: str) -> bool:
    """True if the photo suits the frame orientation (square photos suit both)."""
    with Image.open(path) as img:
        width, height = img.size
        if img.getexif().get(0x0112) in (5, 6, 7, 8):
            width, height = height, width
    shape = classify(width, height)
    return shape in (None, "square", orientation)
