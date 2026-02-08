#!/bin/bash
#
# BLE Poller Installation Script
#
# Installs the BLE poller service on a Raspberry Pi.
# Run as root or with sudo.
#
# Usage:
#   sudo ./install.sh
#

set -euo pipefail

# Configuration
INSTALL_DIR="/opt/ble-poller"
SERVICE_USER="ble-poller"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if running as root
if [[ $EUID -ne 0 ]]; then
    log_error "This script must be run as root (use sudo)"
    exit 1
fi

log_info "Starting BLE Poller installation..."

# Install system dependencies
log_info "Installing system dependencies..."
apt-get update
apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    python3-dev \
    bluetooth \
    bluez \
    libglib2.0-dev \
    libdbus-1-dev

# Enable and start Bluetooth
log_info "Enabling Bluetooth service..."
systemctl enable bluetooth
systemctl start bluetooth

# Create service user
if ! id "$SERVICE_USER" &>/dev/null; then
    log_info "Creating service user: $SERVICE_USER"
    useradd --system --no-create-home --shell /usr/sbin/nologin "$SERVICE_USER"
fi

# Add user to bluetooth group
usermod -a -G bluetooth "$SERVICE_USER"

# Create installation directory
log_info "Creating installation directory: $INSTALL_DIR"
mkdir -p "$INSTALL_DIR"

# Copy application files
log_info "Copying application files..."
cp "$SCRIPT_DIR/ble_poller.py" "$INSTALL_DIR/"
cp "$SCRIPT_DIR/tuya_ble.py" "$INSTALL_DIR/"
cp "$SCRIPT_DIR/mqtt_publisher.py" "$INSTALL_DIR/"
cp "$SCRIPT_DIR/requirements.txt" "$INSTALL_DIR/"

# Copy config template if config doesn't exist
if [[ ! -f "$INSTALL_DIR/config.yaml" ]]; then
    if [[ -f "$SCRIPT_DIR/config.yaml" ]]; then
        cp "$SCRIPT_DIR/config.yaml" "$INSTALL_DIR/"
    else
        cp "$SCRIPT_DIR/config.yaml.example" "$INSTALL_DIR/config.yaml"
        log_warn "Created config.yaml from template - please edit it!"
    fi
fi

# Create Python virtual environment
log_info "Creating Python virtual environment..."
python3 -m venv "$INSTALL_DIR/venv"

# Install Python dependencies
log_info "Installing Python dependencies..."
"$INSTALL_DIR/venv/bin/pip" install --upgrade pip
"$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt"

# Set permissions
log_info "Setting permissions..."
chown -R "$SERVICE_USER:bluetooth" "$INSTALL_DIR"
chmod 750 "$INSTALL_DIR"
chmod 640 "$INSTALL_DIR/config.yaml"
chmod 755 "$INSTALL_DIR/ble_poller.py"

# Install systemd service
log_info "Installing systemd service..."
cp "$SCRIPT_DIR/ble-poller.service" /etc/systemd/system/

# Reload systemd
systemctl daemon-reload

# Enable service (but don't start yet)
systemctl enable ble-poller.service

log_info "Installation complete!"
echo ""
echo "Next steps:"
echo "  1. Edit the configuration file:"
echo "     sudo nano $INSTALL_DIR/config.yaml"
echo ""
echo "  2. Scan for Tuya devices to find MAC addresses:"
echo "     sudo $INSTALL_DIR/venv/bin/python $INSTALL_DIR/ble_poller.py --scan"
echo ""
echo "  3. Test with a single poll:"
echo "     sudo $INSTALL_DIR/venv/bin/python $INSTALL_DIR/ble_poller.py --once"
echo ""
echo "  4. Start the service:"
echo "     sudo systemctl start ble-poller"
echo ""
echo "  5. Check logs:"
echo "     sudo journalctl -u ble-poller -f"
