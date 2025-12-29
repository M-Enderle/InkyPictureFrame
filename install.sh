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
apt-get install -y imagemagick libheif1 python3-dev

# Create images directory
echo "=== Creating directories ==="
mkdir -p "$SCRIPT_DIR/images"
mkdir -p "$SCRIPT_DIR/logs"
chown -R "$USER:$USER" "$SCRIPT_DIR/images" "$SCRIPT_DIR/logs"

# Install Python dependencies
echo "=== Installing Python dependencies ==="
sudo -u "$USER" "$VENV_PATH/bin/pip" install --upgrade pip
sudo -u "$USER" "$VENV_PATH/bin/pip" install pillow requests immich-python-sdk python-dotenv

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
WorkingDirectory=$SCRIPT_DIR/frame
Environment="PATH=$VENV_PATH/bin:/usr/local/bin:/usr/bin:/bin"
ExecStart=$VENV_PATH/bin/python client.py

# Restart on failure
Restart=always
RestartSec=10

# Logging
StandardOutput=append:$SCRIPT_DIR/logs/frame.log
StandardError=append:$SCRIPT_DIR/logs/frame.log

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
echo "To start now, run: sudo systemctl start $SERVICE_NAME"
