#!/bin/bash

# RECKON Client - Systemd Service Installer
# Run with: sudo ./scripts/install-service.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
SERVICE_FILE="$PROJECT_DIR/reckon-client.service"
SYSTEMD_DIR="/etc/systemd/system"

echo "=== RECKON Client Service Installer ==="
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "Error: Please run as root (sudo)"
    exit 1
fi

# Check if service file exists
if [ ! -f "$SERVICE_FILE" ]; then
    echo "Error: Service file not found at $SERVICE_FILE"
    exit 1
fi

# Copy service file
echo "1. Copying service file to $SYSTEMD_DIR..."
cp "$SERVICE_FILE" "$SYSTEMD_DIR/reckon-client.service"

# Reload systemd
echo "2. Reloading systemd daemon..."
systemctl daemon-reload

# Enable service
echo "3. Enabling service to start on boot..."
systemctl enable reckon-client

echo ""
echo "=== Installation Complete ==="
echo ""
echo "Commands:"
echo "  Start:   sudo systemctl start reckon-client"
echo "  Stop:    sudo systemctl stop reckon-client"
echo "  Status:  sudo systemctl status reckon-client"
echo "  Logs:    sudo journalctl -u reckon-client -f"
echo ""
