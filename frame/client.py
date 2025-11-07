"""Random-folder image viewer with .env config and failsafes.

Reads configuration from a .env file (overridable with environment variables):

  IMAGE_FOLDER - folder containing images (default: ./images)
  INTERVAL     - seconds between image changes (default: 30)
  FULLSCREEN   - true/false (default: False)
  WINDOW_WIDTH - initial window width (default: 800)
  WINDOW_HEIGHT- initial window height (default: 600)

The script uses tkinter + Pillow for cross-platform display and schedules
periodic image changes with robust error handling.
"""

from __future__ import annotations

import logging
import os
import random
import signal
import sys
import threading
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv
from PIL import Image, ImageTk

try:
    import tkinter as tk
except Exception:  # pragma: no cover - GUI import will surface at runtime
    tk = None  # type: ignore

load_dotenv()  # load .env into environment if present

LOGGER = logging.getLogger("frame.client")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def _get_env(name: str, default: Optional[str] = None) -> Optional[str]:
    return os.environ.get(name, default)


class ImageCycler:
    """Responsible for selecting images and serving them to the UI."""

    SUPPORTED_EXT = (".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp")

    def __init__(self, folder: Path):
        self.folder = folder
        self._lock = threading.Lock()
        self._files: List[Path] = []
        self.refresh_file_list()

    def refresh_file_list(self) -> None:
        with self._lock:
            if not self.folder.exists() or not self.folder.is_dir():
                LOGGER.warning("Image folder %s missing or not a directory", self.folder)
                self._files = []
                return
            files = [p for p in self.folder.iterdir() if p.suffix.lower() in self.SUPPORTED_EXT and p.is_file()]
            self._files = sorted(files)
            LOGGER.info("Found %d images in %s", len(self._files), self.folder)

    def random_image_path(self) -> Optional[Path]:
        with self._lock:
            if not self._files:
                return None
            return random.choice(self._files)


class ViewerApp:
    def __init__(self) -> None:
        if tk is None:
            raise RuntimeError("tkinter not available; GUI cannot run")

        # Config
        folder = Path(_get_env("IMAGE_FOLDER", "./images")).expanduser()
        interval = float(_get_env("INTERVAL", "30"))
        fullscreen = _get_env("FULLSCREEN", "False").lower() in ("1", "true", "yes")
        width = int(_get_env("WINDOW_WIDTH", "800"))
        height = int(_get_env("WINDOW_HEIGHT", "600"))

        self.folder = folder
        self.interval = max(1.0, interval)
        self.fullscreen = fullscreen
        self.size = (width, height)

        self.cycler = ImageCycler(self.folder)

        self.root = tk.Tk()
        self.root.title("Image Cycler")
        if self.fullscreen:
            self.root.attributes("-fullscreen", True)
        else:
            self.root.geometry(f"{width}x{height}")

        self.canvas = tk.Canvas(self.root, bg="black")
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # Keep reference to PhotoImage to avoid GC
        self._photo = None
        self._job = None

        # Bind resize to redraw
        self.root.bind("<Configure>", self._on_configure)

        # Graceful stop on SIGINT/SIGTERM
        signal.signal(signal.SIGINT, self._signal_handler)
        try:
            signal.signal(signal.SIGTERM, self._signal_handler)
        except Exception:
            # SIGTERM may not be available on Windows; ignore
            pass

    def _signal_handler(self, signum, frame):
        LOGGER.info("Signal %s received, exiting...", signum)
        self.stop()

    def _on_configure(self, event):
        # Called on resize; just redraw current image scaled
        if self._photo:
            self._draw_current_image()

    def start(self):
        LOGGER.info("Starting viewer: folder=%s interval=%s fullscreen=%s", self.folder, self.interval, self.fullscreen)
        self._schedule_next(0)  # show immediately
        self.root.mainloop()

    def stop(self):
        if self._job:
            self.root.after_cancel(self._job)
            self._job = None
        try:
            self.root.quit()
        except Exception:
            pass

    def _schedule_next(self, delay_seconds: float | int):
        ms = int(max(0, delay_seconds) * 1000)
        if self._job:
            self.root.after_cancel(self._job)
        self._job = self.root.after(ms, self._update_image)

    def _update_image(self):
        try:
            path = self.cycler.random_image_path()
            if path is None:
                # No image: refresh list and retry later
                LOGGER.warning("No images found in %s. Retrying in %s seconds.", self.folder, self.interval)
                self.cycler.refresh_file_list()
                self._schedule_next(self.interval)
                return

            LOGGER.info("Displaying %s", path)
            # Open and fully load the image into memory, then delete the file
            pil_img = Image.open(path).convert("RGBA")
            pil_img.load()
            self._photo = pil_img  # hold original as PIL Image for scaling
            self._draw_current_image()

            # Attempt to delete the image file after successful display.
            try:
                path.unlink()
                LOGGER.info("Deleted displayed image %s", path)
                # Refresh the cycler's file list so deleted files are removed
                self.cycler.refresh_file_list()
            except Exception:
                LOGGER.exception("Failed to delete image %s after display", path)

        except Exception as exc:  # pragma: no cover - runtime
            LOGGER.exception("Failed to load/display image: %s", exc)
        finally:
            # schedule next regardless
            self._schedule_next(self.interval)

    def _draw_current_image(self):
        if not isinstance(self._photo, Image.Image):
            return
        w = self.canvas.winfo_width() or self.size[0]
        h = self.canvas.winfo_height() or self.size[1]
        img = self._photo.copy()
        img.thumbnail((w, h), Image.LANCZOS)
        tk_img = ImageTk.PhotoImage(img)
        self.canvas.delete("all")
        self.canvas.create_image(w // 2, h // 2, image=tk_img, anchor=tk.CENTER)
        # Keep reference
        self.canvas.image = tk_img


def main():
    # Seed random if user provided a seed
    seed = _get_env("RANDOM_SEED")
    if seed is not None:
        try:
            random.seed(int(seed))
            LOGGER.info("Random seed set to %s", seed)
        except Exception:
            LOGGER.warning("Invalid RANDOM_SEED: %s", seed)

    app = ViewerApp()
    try:
        app.start()
    except Exception:
        LOGGER.exception("Viewer crashed")
        sys.exit(1)


if __name__ == "__main__":
    main()