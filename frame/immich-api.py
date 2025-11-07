
"""Optional helper to download images into the local image folder.

This script is intentionally lightweight and acts as a failsafe helper:
- If `immich_python_sdk` is installed and properly configured via .env, it
  will try to use it to download assets from a given album.
- Otherwise, you can provide a comma-separated list of image URLs via
  the `SAMPLE_IMAGES` environment variable and the script will download
  those into the configured image folder.

Configuration comes from the environment / .env:
  IMAGE_FOLDER  - local folder (default ./images)
  SAMPLE_IMAGES - optional comma-separated URLs to download
  IMMICH_BASE_URL, IMMICH_API_KEY, ALBUM_ID - optional if immich sdk is present
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

LOGGER = logging.getLogger("frame.immich_api")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

IMAGE_FOLDER = Path(os.environ.get("IMAGE_FOLDER", "./images")).expanduser()
IMAGE_FOLDER.mkdir(parents=True, exist_ok=True)

SAMPLE_IMAGES = os.environ.get("SAMPLE_IMAGES")


def download_url(url: str, target: Path) -> bool:
    """Download a single URL to target path. Returns True on success."""
    import requests

    try:
        r = requests.get(url, timeout=20)
        r.raise_for_status()
        with open(target, "wb") as f:
            f.write(r.content)
        LOGGER.info("Saved %s -> %s", url, target)
        return True
    except Exception as exc:
        LOGGER.exception("Failed to download %s: %s", url, exc)
        return False


def download_sample_images():
    if not SAMPLE_IMAGES:
        LOGGER.info("No SAMPLE_IMAGES provided; skipping sample downloader")
        return
    urls = [u.strip() for u in SAMPLE_IMAGES.split(",") if u.strip()]
    for i, url in enumerate(urls, start=1):
        ext = Path(url.split("?")[0]).suffix or ".jpg"
        target = IMAGE_FOLDER / f"sample_{i}{ext}"
        download_url(url, target)


def try_immich_sdk_download():
    """Try to use immich_python_sdk if available. This is best-effort; failures are logged."""
    try:
        import immich_python_sdk
    except Exception:
        LOGGER.info("immich_python_sdk not installed; skip immich download")
        return

    IMMICH_BASE_URL = os.environ.get("IMMICH_BASE_URL")
    IMMICH_API_KEY = os.environ.get("IMMICH_API_KEY")
    ALBUM_ID = os.environ.get("ALBUM_ID")
    if not (IMMICH_BASE_URL and IMMICH_API_KEY and ALBUM_ID):
        LOGGER.warning("IMMICH_BASE_URL/IMMICH_API_KEY/ALBUM_ID not fully configured; skipping immich sdk path")
        return

    try:
        configuration = immich_python_sdk.Configuration(host=f"{IMMICH_BASE_URL}/api")
        configuration.api_key["api_key"] = IMMICH_API_KEY
        with immich_python_sdk.ApiClient(configuration) as api_client:
            albums_api = immich_python_sdk.AlbumsApi(api_client)
            album = albums_api.get_album_info(ALBUM_ID)
            assets = getattr(album, "assets", []) or []
            LOGGER.info("Found %d assets in album %s", len(assets), ALBUM_ID)
            assets_api = immich_python_sdk.AssetsApi(api_client)
            for asset in assets:
                filename = getattr(asset, "original_file_name", None) or f"asset_{asset.id}.jpg"
                outpath = IMAGE_FOLDER / filename
                LOGGER.info("Downloading asset %s -> %s", asset.id, outpath)
                data = assets_api.download_asset(asset.id)
                with open(outpath, "wb") as f:
                    f.write(data)
    except Exception:
        LOGGER.exception("immich SDK download failed")


def main():
    # First try immich sdk path, then fall back to sample images list.
    try_immich_sdk_download()
    download_sample_images()


if __name__ == "__main__":
    main()