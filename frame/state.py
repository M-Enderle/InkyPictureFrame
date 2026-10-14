"""Persistent runtime state (survives restarts, editable from Home Assistant)."""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any

log = logging.getLogger("frame.state")

HISTORY_LIMIT = 20


class Store:
    """A tiny JSON-backed key/value store with atomic writes."""

    def __init__(self, path: Path, defaults: dict[str, Any]):
        self._path = path
        self._lock = threading.Lock()
        self._data: dict[str, Any] = dict(defaults)
        try:
            self._data.update(json.loads(path.read_text()))
        except FileNotFoundError:
            pass
        except (OSError, ValueError):
            log.warning("Could not read %s, starting from defaults", path)

    def get(self, key: str) -> Any:
        with self._lock:
            return self._data.get(key)

    def update(self, **values: Any) -> None:
        with self._lock:
            self._data.update(values)
            tmp = self._path.with_suffix(".tmp")
            try:
                tmp.write_text(json.dumps(self._data, indent=2))
                tmp.replace(self._path)
            except OSError:
                log.exception("Could not persist state to %s", self._path)
