"""Frame controller: owns the slideshow loop and all state shown in Home Assistant."""

from __future__ import annotations

import logging
import queue
import random
import shutil
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import render
from .config import MAX_INTERVAL_MIN, MIN_INTERVAL_MIN, VERSION, Settings
from .immich import ImmichClient, ImmichError
from .led import Led
from .state import HISTORY_LIMIT, Store

log = logging.getLogger("frame.controller")

ALBUM_TTL = 3600  # seconds between automatic album refreshes
RETRY_DELAY = 60  # seconds before retrying after an error


def _iso(ts: float | None) -> str | None:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat() if ts else None


class Controller:
    def __init__(self, settings: Settings, display, led: Led, immich: ImmichClient | None):
        self.settings = settings
        self.display = display
        self.led = led
        self.immich = immich
        self.store = Store(
            settings.data_dir / "state.json",
            {
                "interval_min": settings.interval_min,
                "orientation": settings.orientation,
                "album_id": settings.album_id,
                "slideshow": True,
                "display_on": True,
                "led_on": False,
                "led_brightness": 128,
                "history": [],
                "current": None,
                "last_change": None,
            },
        )
        self._cmds: queue.Queue[tuple[str, Any]] = queue.Queue()
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

        self._status = "starting"
        self._last_error: str | None = None
        self._album_name: str | None = None
        self._album_ids: list[str] = []
        self._albums: list[dict[str, str]] = []
        self._album_fetched = 0.0
        self._bag: list[str] = []
        self._preview: bytes | None = None
        self._next_change: float | None = None

    # ------------------------------------------------------------------ public

    def start(self) -> None:
        self.led.apply(bool(self.store.get("led_on")), int(self.store.get("led_brightness")))
        self._thread = threading.Thread(target=self._run, name="frame-loop", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._cmds.put(("stop", None))
        if self._thread:
            self._thread.join(timeout=5)
        self.led.close()

    def submit(self, name: str, payload: Any = None) -> None:
        self._cmds.put((name, payload))

    def preview(self) -> tuple[bytes, str] | None:
        with self._lock:
            if self._preview is None:
                return None
            return self._preview, str(int(self.store.get("last_change") or 0))

    def set_led(self, on: bool | None, brightness: int | None) -> None:
        if on is not None:
            self.store.update(led_on=on)
        if brightness is not None:
            self.store.update(led_brightness=max(1, min(255, brightness)))
            if on is None:  # setting a brightness implies switching on, like a light
                self.store.update(led_on=True)
        self.led.apply(bool(self.store.get("led_on")), int(self.store.get("led_brightness")))

    def snapshot(self) -> dict[str, Any]:
        s = self.store
        with self._lock:
            return {
                "id": self.settings.device_id,
                "name": self.settings.device_name,
                "version": VERSION,
                "model": self.display.model,
                "resolution": list(self.display.resolution),
                "status": self._status,
                "last_error": self._last_error,
                "display_on": s.get("display_on"),
                "slideshow": s.get("slideshow"),
                "interval_min": s.get("interval_min"),
                "min_interval_min": MIN_INTERVAL_MIN,
                "max_interval_min": MAX_INTERVAL_MIN,
                "orientation": s.get("orientation"),
                "album_id": s.get("album_id"),
                "album_name": self._album_name,
                "album_count": len(self._album_ids),
                "albums": list(self._albums),
                "current": s.get("current"),
                "last_change": _iso(s.get("last_change")),
                "next_change": _iso(self._next_change)
                if s.get("slideshow") and s.get("display_on")
                else None,
                "led": {
                    "available": self.led.available,
                    "on": bool(s.get("led_on")),
                    "brightness": s.get("led_brightness"),
                },
            }

    # -------------------------------------------------------------- main loop

    def _run(self) -> None:
        try:
            self._startup()
        except Exception:
            log.exception("Startup failed")
            self._fail("Start fehlgeschlagen, siehe Log")
        while not self._stop.is_set():
            try:
                cmd = self._cmds.get(timeout=self._timeout())
            except queue.Empty:
                cmd = ("next", None) if self._due() else None
            if cmd is None:
                continue
            batch = [cmd]
            while not self._cmds.empty():
                batch.append(self._cmds.get_nowait())
            # Pressing "next" repeatedly while an e-ink refresh runs should not queue up
            # a pile of 30-second redraws.
            seen_next = False
            for name, payload in batch:
                if name == "next":
                    if seen_next:
                        continue
                    seen_next = True
                if name == "stop":
                    return
                try:
                    self._handle(name, payload)
                except Exception as err:
                    log.exception("Command %s failed", name)
                    self._fail(str(err))

    def _timeout(self) -> float:
        if self._next_change and self.store.get("slideshow") and self.store.get("display_on"):
            return min(60.0, max(0.1, self._next_change - time.time()))
        return 60.0

    def _due(self) -> bool:
        return bool(
            self.store.get("slideshow")
            and self.store.get("display_on")
            and self._next_change
            and time.time() >= self._next_change
        )

    def _startup(self) -> None:
        """Restore the last picture's preview without redrawing the e-ink panel."""
        last = self.store.get("last_change")
        source = self._source_path()
        if self.store.get("display_on") and source and self.store.get("current"):
            self._set_preview(source)
            self._set_status("idle")
            self._schedule(last)
            if self._due():
                self._handle("next", None)
        elif not self.store.get("display_on"):
            self._set_preview(None)
            self._set_status("off")
        else:
            self._handle("next", None)

    # --------------------------------------------------------------- commands

    def _handle(self, name: str, payload: Any) -> None:
        s = self.store
        if name == "next" or name == "previous":
            if not s.get("display_on"):
                return
            self._advance(previous=name == "previous")
        elif name == "reload":
            self._ensure_album(force=True)
        elif name == "clear":
            self._power(False)
        elif name == "settings":
            self._apply_settings(payload)

    def _apply_settings(self, new: dict[str, Any]) -> None:
        s = self.store
        redraw = False
        if "interval_min" in new:
            s.update(interval_min=min(max(int(new["interval_min"]), MIN_INTERVAL_MIN), MAX_INTERVAL_MIN))
            self._schedule(s.get("last_change"))
        if "orientation" in new and new["orientation"] != s.get("orientation"):
            s.update(orientation=new["orientation"])
            redraw = True
        if "slideshow" in new:
            s.update(slideshow=bool(new["slideshow"]))
            self._schedule(s.get("last_change"))
        if "album_id" in new and new["album_id"] != s.get("album_id"):
            s.update(album_id=new["album_id"], history=[])
            self._bag = []
            self._ensure_album(force=True)
            if s.get("display_on"):
                self._advance()
            return
        if "display_on" in new and bool(new["display_on"]) != bool(s.get("display_on")):
            self._power(bool(new["display_on"]))
            return
        if redraw and s.get("display_on") and self._source_path():
            self._redraw_current()

    def _power(self, on: bool) -> None:
        s = self.store
        if on:
            s.update(display_on=True)
            if self._source_path() and s.get("current"):
                self._redraw_current()
            else:
                self._advance()
        else:
            self._set_status("updating")
            self.display.clear()
            s.update(display_on=False)
            self._set_preview(None)
            self._set_status("off")

    # ---------------------------------------------------------------- slideshow

    def _advance(self, previous: bool = False) -> None:
        s = self.store
        self._set_status("updating")
        try:
            self._ensure_album()
            history: list[str] = list(s.get("history") or [])
            if previous:
                if len(history) < 2:
                    self._set_status("idle")
                    return
                history.pop()
                asset_id = history[-1]
                path = self._download(asset_id)
            else:
                asset_id, path = self._next_asset()
                history.append(asset_id)
            info = self.immich.asset_info(asset_id) if self.immich else {}
            info.update(id=asset_id, url=f"{self.immich.base_url}/photos/{asset_id}" if self.immich else None)
            self._show(path)
            now = time.time()
            s.update(
                history=history[-HISTORY_LIMIT:], current=info, last_change=now
            )
            self._schedule(now)
            self._last_error = None
            self._set_status("idle")
        except (ImmichError, OSError) as err:
            log.warning("Advance failed: %s", err)
            self._fail(str(err))

    def _next_asset(self) -> tuple[str, Path]:
        """Draw from a shuffled bag; skip assets that vanished from Immich."""
        for _ in range(3):
            if not self._bag:
                self._bag = random.sample(self._album_ids, len(self._album_ids))
                current = (self.store.get("current") or {}).get("id")
                if len(self._bag) > 1 and self._bag[-1] == current:
                    self._bag[0], self._bag[-1] = self._bag[-1], self._bag[0]
            asset_id = self._bag.pop()
            try:
                return asset_id, self._download(asset_id)
            except ImmichError as err:
                log.warning("Skipping asset %s: %s", asset_id, err)
        raise ImmichError("Kein Bild konnte geladen werden")

    def _download(self, asset_id: str) -> Path:
        if self.immich is None:
            raise ImmichError("Immich ist nicht konfiguriert")
        return self.immich.download(asset_id, self.settings.images_dir)

    def _show(self, downloaded: Path) -> None:
        """Render a downloaded file, push it to the panel and keep it as the source."""
        orientation = self.store.get("orientation")
        preview, device = render.prepare(downloaded, self.display.resolution, orientation)
        self.display.show(device)
        self._keep_source(downloaded)
        with self._lock:
            self._preview = render.to_jpeg(preview)

    def _redraw_current(self) -> None:
        source = self._source_path()
        if source is None:
            return
        self._set_status("updating")
        preview, device = render.prepare(
            source, self.display.resolution, self.store.get("orientation")
        )
        self.display.show(device)
        with self._lock:
            self._preview = render.to_jpeg(preview)
        now = time.time()
        self.store.update(last_change=now)
        self._schedule(now)
        self._set_status("idle")

    def _keep_source(self, downloaded: Path) -> None:
        images = self.settings.images_dir
        for old in images.glob("current.*"):
            old.unlink(missing_ok=True)
        shutil.move(str(downloaded), images / f"current{downloaded.suffix}")

    def _source_path(self) -> Path | None:
        found = sorted(self.settings.images_dir.glob("current.*"))
        return found[0] if found else None

    def _set_preview(self, source: Path | None) -> None:
        with self._lock:
            if source is None:
                self._preview = render.to_jpeg(render.blank(self.display.resolution))
                return
            preview, _ = render.prepare(
                source, self.display.resolution, self.store.get("orientation")
            )
            self._preview = render.to_jpeg(preview)

    # ------------------------------------------------------------------ helpers

    def _ensure_album(self, force: bool = False) -> None:
        if self.immich is None:
            raise ImmichError("IMMICH_BASE_URL und IMMICH_API_KEY sind nicht gesetzt")
        if not force and self._album_ids and time.time() - self._album_fetched < ALBUM_TTL:
            return
        try:
            self._albums = self.immich.albums()
        except ImmichError:
            log.warning("Could not list albums", exc_info=True)
        album_id = self.store.get("album_id")
        try:
            name, ids = self.immich.album_images(album_id)
        except ImmichError:
            if self._album_ids:  # keep running from the cached list while Immich is down
                log.warning("Immich unavailable, using cached album", exc_info=True)
                return
            raise
        if not ids:
            raise ImmichError(f"Album „{name}“ enthält keine Bilder")
        if set(ids) != set(self._album_ids):
            self._bag = []
        self._album_name, self._album_ids = name, ids
        self._album_fetched = time.time()
        log.info("Album %s: %d images", name, len(ids))

    def _schedule(self, last_change: float | None) -> None:
        interval = int(self.store.get("interval_min")) * 60
        now = time.time()
        self._next_change = max((last_change or now) + interval, now + 5)

    def _set_status(self, status: str) -> None:
        with self._lock:
            self._status = status

    def _fail(self, message: str) -> None:
        with self._lock:
            self._status = "error"
            self._last_error = message
        self._next_change = time.time() + RETRY_DELAY
