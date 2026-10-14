# Inky Picture Frame

A Raspberry Pi–powered digital picture frame that displays random photos from an [Immich](https://immich.app/) album on a [Pimoroni Inky](https://shop.pimoroni.com/collections/inky) e-ink display.

## Features

- Fetches images randomly from a configured Immich album
- Supports both landscape and portrait orientations
- Automatically converts HEIC/HEIF images to JPEG via ImageMagick
- Runs as a systemd service with automatic restart on failure
- Rotating log files for easy debugging
- **Home Assistant integration** (custom component): live preview, next/previous, display on/off, interval, album, orientation, optional dimmable LED — see [docs/home-assistant.md](docs/home-assistant.md)

## Hardware Requirements

- Raspberry Pi (any model with GPIO, tested on Pi Zero 2 W / Pi 4)
- [Pimoroni Inky Impression](https://shop.pimoroni.com/products/inky-impression-5-7) or any other compatible Inky display
- MicroSD card with Raspberry Pi OS

## Software Requirements

- Raspberry Pi OS (Bookworm or later recommended)
- Python 3.10+
- [Pimoroni Inky library](https://github.com/pimoroni/inky) installed in a virtual environment (default: `/home/pi/.virtualenvs/pimoroni`)
- ImageMagick (installed automatically by `install.sh`)
- A running [Immich](https://immich.app/) instance with at least one album

## Installation

1. **Clone the repository** onto your Raspberry Pi:

   ```bash
   git clone https://github.com/M-Enderle/InkyPictureFrame.git
   cd InkyPictureFrame
   ```

2. **Create the configuration file** (see [Configuration](#configuration)):

   ```bash
   cp frame/.env.example frame/.env
   nano frame/.env
   ```

3. **Run the installer** as root:

   ```bash
   sudo bash install.sh
   ```

   The script will:
   - Install system dependencies (`imagemagick`, `libheif1`, `python3-dev`)
   - Create the `images/` and `logs/` directories
   - Install Python dependencies into the Pimoroni virtual environment
   - Register and enable the `inky-frame` systemd service

4. **Start the service**:

   ```bash
   sudo systemctl start inky-frame
   ```

### Custom virtual environment path

If your Pimoroni virtual environment lives somewhere other than `/home/pi/.virtualenvs/pimoroni`, pass the path via an environment variable:

```bash
sudo VENV_PATH=/path/to/venv bash install.sh
```

## Configuration

Create `frame/.env` with the following variables:

| Variable         | Required | Default     | Description                                      |
|------------------|----------|-------------|--------------------------------------------------|
| `IMMICH_BASE_URL`| Yes      | —           | Base URL of your Immich instance (e.g. `https://immich.example.com`) |
| `IMMICH_API_KEY` | Yes      | —           | API key generated in Immich → Account → API Keys |
| `ALBUM_ID`       | Yes      | —           | UUID of the Immich album to display photos from  |
| `ORIENTATION`    | No       | `landscape` | `landscape` or `portrait`                        |
| `INTERVAL_MINUTES` | No     | `15`        | Minutes between photos (3–1440)                  |
| `API_PORT`       | No       | `8765`      | Port of the Home Assistant API                   |
| `FRAME_API_TOKEN`| No       | generated   | Token for the API; show it with `python -m frame token` |
| `LED_GPIO`       | No       | —           | BCM pin of an optional dimmable LED, see [docs/led.md](docs/led.md) |

**Example `frame/.env`:**

```dotenv
IMMICH_BASE_URL=https://immich.example.com
IMMICH_API_KEY=your_api_key_here
ALBUM_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
ORIENTATION=landscape
```

> **Tip:** You can find the Album ID in Immich by opening the album and copying the UUID from the URL.

## Service Management

| Action        | Command                                 |
|---------------|-----------------------------------------|
| Start         | `sudo systemctl start inky-frame`       |
| Stop          | `sudo systemctl stop inky-frame`        |
| Restart       | `sudo systemctl restart inky-frame`     |
| Status        | `sudo systemctl status inky-frame`      |
| View logs     | `tail -f logs/frame.log`                |

The service is configured to restart automatically on failure (10-second delay between attempts) and starts on boot.

## Project Structure

```
InkyPictureFrame/
├── frame/
│   ├── client.py      # Controller: slideshow loop and state
│   ├── api.py         # HTTP API for Home Assistant (FastAPI)
│   ├── immich.py      # Immich REST client
│   ├── render.py      # Crop/rotate for the panel
│   ├── display.py     # Inky panel (or mock for development)
│   ├── led.py         # Optional dimmable LED
│   └── discovery.py   # mDNS announcement
├── custom_components/inky_frame/   # Home Assistant integration (HACS)
├── docs/              # Home Assistant, LED wiring, ideas
├── logs/              # Rotating log files (created at install time)
├── images/            # Temporary image downloads (created at install time)
├── install.sh         # Installation & systemd setup script
└── pyproject.toml     # Python project metadata (Poetry)
```

## How It Works

1. On startup, `client.py` connects to the Inky display via `inky.auto`.
2. Every `INTERVAL_MINUTES` (default 15; changeable from Home Assistant) the main loop:
   - Fetches the image asset IDs of the configured Immich album (videos are skipped).
   - Keeps only photos that match the frame orientation (landscape mode shows landscape photos, portrait mode portrait photos; square photos suit both).
   - Picks the next one from a shuffled bag (no repeats until the album is through).
   - Downloads Immich's display-sized preview (falls back to the original + HEIC→JPEG conversion).
   - Centre-crops and resizes the image to match the display resolution.
   - Rotates the image 90° when `ORIENTATION=portrait`.
   - Pushes the image to the Inky display.

## Troubleshooting

- **Display not detected:** Make sure the Inky HAT is properly seated and that the Pimoroni library is installed in the virtual environment used by the service.
- **API errors:** Check `logs/frame.log` for detailed error messages. Verify that `IMMICH_BASE_URL`, `IMMICH_API_KEY`, and `ALBUM_ID` are correct.
- **HEIC conversion fails:** Ensure `imagemagick` and `libheif1` are installed (`sudo apt-get install -y imagemagick libheif1`).
- **Service won't start:** Run `sudo journalctl -u inky-frame -e` or inspect `logs/frame.log`.
- **Development without hardware:** `MOCK_DISPLAY=1 python -m frame` writes `data/mock_display.png`.

## License

This project is open source. See [LICENSE](LICENSE) for details.
