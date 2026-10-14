"""Display backends: the real Inky panel or a mock for development."""

from __future__ import annotations

import logging
from pathlib import Path

from PIL import Image

from .render import blank

log = logging.getLogger("frame.display")


class InkyDisplay:
    def __init__(self) -> None:
        from inky.auto import auto

        self._inky = auto()
        self.resolution: tuple[int, int] = tuple(self._inky.resolution)  # type: ignore[assignment]
        self.model = type(self._inky).__name__
        log.info("Detected Inky display: %s %s", self.model, self.resolution)

    def show(self, image: Image.Image) -> None:
        self._inky.set_image(image)
        self._inky.show()

    def clear(self) -> None:
        self.show(blank(self.resolution))


class MockDisplay:
    """Writes the frame to data/mock_display.png instead of driving hardware."""

    def __init__(self, data_dir: Path, resolution: tuple[int, int] = (800, 480)):
        self.resolution = resolution
        self.model = "MockDisplay"
        self._out = data_dir / "mock_display.png"

    def show(self, image: Image.Image) -> None:
        image.save(self._out)

    def clear(self) -> None:
        self.show(blank(self.resolution))


def create_display(mock: bool, data_dir: Path) -> InkyDisplay | MockDisplay:
    if mock:
        return MockDisplay(data_dir)
    return InkyDisplay()
