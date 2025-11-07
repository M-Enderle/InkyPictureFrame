import logging
import logging.handlers
import os
import time
from pathlib import Path
from typing import List, Optional

import dotenv
import immich_python_sdk
from immich_python_sdk.rest import ApiException

dotenv.load_dotenv()

# Hardcoded Immich settings (from project .env as requested)
IMMICH_BASE_URL = os.getenv("IMMICH_BASE_URL", "https://immich.enderles.com")
IMMICH_API_KEY = os.getenv("IMMICH_API_KEY", "")
ALBUM_ID = os.getenv("ALBUM_ID", "")

# Configure the SDK to talk to the Immich instance and use the API key
# The server's API routes are under the /api prefix, so include that in host
configuration = immich_python_sdk.Configuration(host=f"{IMMICH_BASE_URL}/api")

# Set the API key directly (hardcoded)
configuration.api_key["api_key"] = IMMICH_API_KEY

# Logging configuration: file + console, with rotation to keep logs bounded
LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "immich-api.log"

logger = logging.getLogger("immich_api")
if not logger.handlers:
    logger.setLevel(logging.DEBUG)
    # Rotating file handler
    try:
        fh = logging.handlers.RotatingFileHandler(
            filename=str(LOG_FILE),
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
    except Exception:
        fh = logging.FileHandler(filename=str(LOG_FILE), encoding="utf-8")

    fh.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s [%(name)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    # Also log warnings and up to console
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(formatter)
    logger.addHandler(ch)


def _retry(
    func, retries: int = 3, delay: float = 0.5, backoff: float = 2.0, *args, **kwargs
):
    """Simple retry helper with exponential backoff.

    Returns whatever func returns, or raises the last exception after retries.
    """
    attempt = 0
    while True:
        try:
            return func(*args, **kwargs)
        except Exception as e:
            attempt += 1
            if attempt > retries:
                logger.exception("Operation failed after %d attempts", attempt)
                raise
            wait = delay * (backoff ** (attempt - 1))
            logger.warning(
                "Operation failed (attempt %d/%d): %s — retrying in %.1fs",
                attempt,
                retries,
                e,
                wait,
            )
            time.sleep(wait)


def get_image_ids() -> List[str]:
    """Fetch and return a list of image asset IDs from the specified album.

    This function is resilient to API errors and will return an empty list
    if the album is empty or the call fails.
    """
    image_ids: List[str] = []
    try:

        def _call():
            with immich_python_sdk.ApiClient(configuration) as api_client:
                api_instance = immich_python_sdk.AlbumsApi(api_client)
                return api_instance.get_album_info(ALBUM_ID)

        api_response = _retry(_call)
        assets = getattr(api_response, "assets", []) or []

        for asset in assets:
            try:
                image_ids.append(asset.id)
            except Exception:
                logger.exception("Failed to read asset id from asset: %r", asset)
    except ApiException as e:
        logger.exception("API error while fetching album info: %s", e)
    except Exception as e:
        logger.exception("Unexpected error while fetching image ids: %s", e)

    logger.info("Found %d image ids in album %s", len(image_ids), ALBUM_ID)
    return image_ids


def _safe_write(path: Path, data: bytes) -> None:
    """Write bytes to path atomically (best-effort)."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        with tmp.open("wb") as f:
            f.write(data)
        tmp.replace(path)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except Exception:
                pass


def download_image(asset_id: str) -> Optional[str]:
    """Download the image asset with the given ID and save it to a file.

    Returns the filesystem path to the downloaded file, or None on failure.
    """
    images_dir = Path(__file__).resolve().parent.parent / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    try:

        def _call_get():
            with immich_python_sdk.ApiClient(configuration) as api_client:
                api_instance = immich_python_sdk.AssetsApi(api_client)
                return api_instance.get_asset_info(asset_id)

        asset = _retry(_call_get)

        # Fallback filename
        raw_name = getattr(asset, "original_file_name", None) or f"{asset.id}"
        safe_name = os.path.basename(raw_name)
        if not safe_name:
            safe_name = f"{asset.id}"

        dest = images_dir / safe_name

        def _call_download():
            with immich_python_sdk.ApiClient(configuration) as api_client:
                api_instance = immich_python_sdk.AssetsApi(api_client)
                return api_instance.download_asset(asset_id)

        api_response = _retry(_call_download)

        if api_response is None:
            logger.error("Download returned no data for asset %s", asset_id)
            return None

        # api_response may be bytes or a stream-like object. Try to handle bytes first.
        if isinstance(api_response, (bytes, bytearray)):
            _safe_write(dest, bytes(api_response))
        else:
            # Attempt to read from stream-like object
            try:
                data = api_response.read()
            except Exception:
                # Last resort: try to write directly
                try:
                    with open(dest, "wb") as f:
                        f.write(api_response)
                except Exception:
                    logger.exception(
                        "Failed to write download result for asset %s", asset_id
                    )
                    return None
            else:
                _safe_write(dest, data)

        logger.info("Downloaded asset %s to %s", asset_id, dest)
        return str(dest)
    except ApiException as e:
        logger.exception("API error while downloading asset %s: %s", asset_id, e)
    except IOError as e:
        logger.exception("I/O error while saving asset %s: %s", asset_id, e)
    except Exception as e:
        logger.exception("Unexpected error while downloading asset %s: %s", asset_id, e)

    return None


def delete_image(path: str) -> bool:
    """Delete the image asset from the local folder (not immich server).

    Returns True if the file was deleted, False otherwise.
    """
    try:
        p = Path(path)
        if p.exists():
            p.unlink()
            logger.info("Deleted image file: %s", path)
            return True
        logger.debug("File to delete does not exist: %s", path)
    except Exception:
        logger.exception("Failed to delete file: %s", path)
    return False


if __name__ == "__main__":
    # Example usage: fetch ids, download first image, then delete it — with robust logging
    logger.info("Starting immich-api script (example run)")
    try:
        image_ids = get_image_ids()
        print(f"Found {len(image_ids)} images in album.")

        if image_ids:
            first_image_id = image_ids[0]
            print(f"Downloading image with ID: {first_image_id}")
            file_path = download_image(first_image_id)
            if file_path:
                print(f"Image downloaded to: {file_path}")

                # Optionally delete the image after download
                deleted = delete_image(file_path)
                print(f"Deleted image file: {file_path}: {deleted}")
            else:
                print("Download failed; see log for details.")
        else:
            print("No images found in album.")
    except Exception:
        logger.exception("Unhandled exception in main")
