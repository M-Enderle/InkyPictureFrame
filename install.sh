#!/bin/bash
set -e

# Inky Picture Frame - Installation Script
# This script installs dependencies, sets up autostart via systemd,
# and configures automatic restart on failure.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="inky-frame"
VENV_PATH="${VENV_PATH:-/home/pi/.virtualenvs/pimoroni}"
USER="${SUDO_USER:-pi}"

echo "=== Inky Picture Frame Installer ==="
echo "Install directory: $SCRIPT_DIR"
echo "Virtual environment: $VENV_PATH"
echo "User: $USER"
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "Please run as root (use sudo)"
    exit 1
fi

# Install system dependencies
echo "=== Installing system dependencies ==="
apt-get update
apt-get install -y imagemagick libheif1 python3-dev python3-venv python3-pip swig liblgpio-dev

# Enable SPI + I2C (needed by the Inky display) and the SPI overlay Pimoroni recommends
echo "=== Enabling SPI / I2C ==="
REBOOT_NEEDED=0
if command -v raspi-config >/dev/null; then
    raspi-config nonint do_spi 0
    raspi-config nonint do_i2c 0
fi
BOOT_CFG=/boot/firmware/config.txt
[ -f "$BOOT_CFG" ] || BOOT_CFG=/boot/config.txt
if [ -f "$BOOT_CFG" ] && ! grep -q "^dtoverlay=spi0-0cs" "$BOOT_CFG"; then
    echo "dtoverlay=spi0-0cs" >> "$BOOT_CFG"
fi
[ -e /dev/spidev0.0 ] || REBOOT_NEEDED=1

# Create images directory
echo "=== Creating directories ==="
mkdir -p "$SCRIPT_DIR/images"
mkdir -p "$SCRIPT_DIR/logs"
chown -R "$USER:$USER" "$SCRIPT_DIR/images" "$SCRIPT_DIR/logs"

# Create the virtual environment (with the Pimoroni Inky library) if it doesn't exist yet
if [ ! -x "$VENV_PATH/bin/pip" ]; then
    echo "=== Creating virtual environment $VENV_PATH ==="
    sudo -u "$USER" mkdir -p "$(dirname "$VENV_PATH")"
    sudo -u "$USER" python3 -m venv "$VENV_PATH"
    sudo -u "$USER" "$VENV_PATH/bin/pip" install --upgrade pip
    sudo -u "$USER" "$VENV_PATH/bin/pip" install "inky[rpi]"
fi

# Install Python dependencies
echo "=== Installing Python dependencies ==="
sudo -u "$USER" "$VENV_PATH/bin/pip" install --upgrade pip
sudo -u "$USER" "$VENV_PATH/bin/pip" install -r "$SCRIPT_DIR/requirements.txt"
# Optional: dimmable LED support (only needed when LED_GPIO is set in .env)
sudo -u "$USER" "$VENV_PATH/bin/pip" install gpiozero lgpio || echo "WARNING: LED support not installed (gpiozero/lgpio failed)"

# Create systemd service file
echo "=== Creating systemd service ==="
cat > /etc/systemd/system/${SERVICE_NAME}.service << EOF
[Unit]
Description=Inky Picture Frame Display
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$SCRIPT_DIR
Environment="PATH=$VENV_PATH/bin:/usr/local/bin:/usr/bin:/bin"
ExecStart=$VENV_PATH/bin/python -m frame

# Restart on failure
Restart=always
RestartSec=10

# Logging: the app writes logs/frame.log itself (rotating); stdout goes to journald
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# Reload systemd and enable service
echo "=== Enabling service ==="
systemctl daemon-reload
systemctl enable ${SERVICE_NAME}.service

# Check for .env file
if [ ! -f "$SCRIPT_DIR/frame/.env" ]; then
    echo ""
    echo "=== WARNING ==="
    echo "No .env file found at $SCRIPT_DIR/frame/.env"
    echo "Please create one with the following variables:"
    echo "  IMMICH_BASE_URL=https://your-immich-server.com"
    echo "  IMMICH_API_KEY=your-api-key"
    echo "  ALBUM_ID=your-album-id"
    echo "  ORIENTATION=landscape  # or portrait"
    echo "(see frame/.env.example)"
    echo ""
fi

echo ""
echo "=== Installation complete ==="
echo ""
echo "Commands:"
echo "  Start:   sudo systemctl start $SERVICE_NAME"
echo "  Stop:    sudo systemctl stop $SERVICE_NAME"
echo "  Status:  sudo systemctl status $SERVICE_NAME"
echo "  Logs:    tail -f $SCRIPT_DIR/logs/frame.log"
echo ""
echo "The service will start automatically on boot."
if [ "$REBOOT_NEEDED" = 1 ]; then
    echo "SPI was just enabled: REBOOT the Pi (sudo reboot) before starting the service."
else
    echo "To start now, run: sudo systemctl start $SERVICE_NAME"
fi
echo ""
echo "Home Assistant: add the 'Inky Picture Frame' integration (HACS) and enter the API token:"
echo "  sudo -u $USER $VENV_PATH/bin/python -m frame token   (run from $SCRIPT_DIR)"
