"""Minimal Immich REST client (albums, asset info, downloads)."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Any

import requests

log = logging.getLogger("frame.immich")

_EXT = {"image/jpeg": ".jpg", "image/webp": ".webp", "image/png": ".png"}


def classify(width: float | None, height: float | None) -> str | None:
    """landscape / portrait / square (within 3 %), None if the size is unknown."""
    if not width or not height:
        return None
    ratio = width / height
    if 0.97 <= ratio <= 1.03:
        return "square"
    return "landscape" if ratio > 1 else "portrait"


def _shape(asset: dict[str, Any]) -> str | None:
    """Shape as displayed, i.e. with the EXIF rotation applied."""
    exif = asset.get("exifInfo") or {}
    width = exif.get("exifImageWidth") or asset.get("width")
    height = exif.get("exifImageHeight") or asset.get("height")
    if exif.get("orientation") in (5, 6, 7, 8, "5", "6", "7", "8") and exif.get("exifImageWidth"):
        width, height = height, width
    return classify(width, height)


class ImmichError(Exception):
    """Raised when Immich can't be reached or answers unexpectedly."""


class ImmichClient:
    def __init__(self, base_url: str, api_key: str, timeout: float = 30.0):
        if not base_url or not api_key:
            raise ImmichError("IMMICH_BASE_URL und IMMICH_API_KEY sind nicht gesetzt")
        self.base_url = base_url
        self._timeout = timeout
        self._session = requests.Session()
        self._session.headers["x-api-key"] = api_key
        self._session.headers["Accept"] = "application/json"

    def _get(self, path: str, **kwargs: Any) -> requests.Response:
        return self._request("GET", path, **kwargs)

    def _request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        last: Exception | None = None
        for attempt in range(3):
            try:
                resp = self._session.request(
                    method, f"{self.base_url}/api{path}", timeout=self._timeout, **kwargs
                )
                if resp.status_code in (401, 403):
                    raise ImmichError("Immich: API-Key ungültig oder ohne Berechtigung")
                if resp.status_code == 404:
                    raise ImmichError(f"Immich: {path} nicht gefunden")
                resp.raise_for_status()
                return resp
            except ImmichError:
                raise
            except requests.RequestException as err:
                last = err
                log.warning("Immich %s failed (attempt %d/3): %s", path, attempt + 1, err)
        raise ImmichError(f"Immich nicht erreichbar: {last}")

    def albums(self) -> list[dict[str, str]]:
        """All albums visible to the API key as [{id, name}]."""
        data = self._get("/albums").json()
        return [{"id": a["id"], "name": a.get("albumName") or a["id"]} for a in data]

    def album_images(self, album_id: str) -> tuple[str, list[dict[str, str | None]]]:
        """Return (album name, [{id, shape}]) — videos and trashed items skipped.

        `shape` is landscape / portrait / square, or None when Immich has no size.
        """
        if not album_id:
            raise ImmichError("Kein Album ausgewählt (ALBUM_ID)")
        data = self._get(f"/albums/{album_id}").json()
        name = data.get("albumName") or album_id
        assets = data.get("assets") or []  # older Immich versions embed the assets
        if not assets and data.get("assetCount"):
            assets = self._search_album(album_id)
        images = [
            {"id": a["id"], "shape": _shape(a)}
            for a in assets
            if a.get("type") == "IMAGE" and not a.get("isTrashed")
        ]
        return name, images

    def _search_album(self, album_id: str) -> list[dict[str, Any]]:
        """Newer Immich versions list album assets only via the metadata search."""
        items: list[dict[str, Any]] = []
        page: str | int | None = 1
        while page:
            body = {"albumIds": [album_id], "type": "IMAGE", "size": 1000, "page": int(page)}
            result = self._request("POST", "/search/metadata", json=body).json()["assets"]
            items.extend(result.get("items") or [])
            page = result.get("nextPage")
        return items

    def asset_info(self, asset_id: str) -> dict[str, Any]:
        """Best-effort metadata for display in Home Assistant."""
        try:
            data = self._get(f"/assets/{asset_id}").json()
        except ImmichError:
            return {}
        exif = data.get("exifInfo") or {}
        place = ", ".join(p for p in (exif.get("city"), exif.get("country")) if p)
        return {
            "filename": data.get("originalFileName") or asset_id,
            "taken": data.get("localDateTime") or data.get("fileCreatedAt"),
            "location": place or None,
            "description": exif.get("description") or None,
        }

    def download(self, asset_id: str, dest_dir: Path) -> Path:
        """Download a display-sized rendition (falls back to the original)."""
        dest_dir.mkdir(parents=True, exist_ok=True)
        try:
            resp = self._get(f"/assets/{asset_id}/thumbnail", params={"size": "preview"})
            suffix = _EXT.get(resp.headers.get("content-type", "").split(";")[0], ".jpg")
            path = dest_dir / f"download{suffix}"
            path.write_bytes(resp.content)
            return path
        except ImmichError:
            log.info("No preview for %s, downloading original", asset_id)
        resp = self._get(f"/assets/{asset_id}/original")
        raw = dest_dir / "download.orig"
        raw.write_bytes(resp.content)
        jpg = dest_dir / "download.jpg"
        try:
            subprocess.run(["convert", str(raw), str(jpg)], check=True, timeout=120)
        except (OSError, subprocess.SubprocessError) as err:
            raise ImmichError(f"Konvertierung fehlgeschlagen: {err}") from err
        finally:
            raw.unlink(missing_ok=True)
        return jpg
