#!/bin/bash
#
# Read-Only Filesystem Setup Script
#
# Configures a Raspberry Pi with an overlay filesystem to protect
# the SD card from wear. All writes go to RAM and are lost on reboot.
#
# Based on:
# - https://www.dzombak.com/blog/2024/03/running-a-raspberry-pi-with-a-read-only-root-filesystem/
# - https://learn.adafruit.com/read-only-raspberry-pi/overview
#
# Usage:
#   sudo ./setup-readonly.sh [enable|disable|status]
#

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

check_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "This script must be run as root"
        exit 1
    fi
}

check_pi() {
    if [[ ! -f /etc/rpi-issue ]]; then
        log_warn "This doesn't appear to be a Raspberry Pi"
        read -p "Continue anyway? [y/N] " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi
}

show_status() {
    echo "Read-Only Filesystem Status:"
    echo "-----------------------------"

    # Check if overlay is active
    if mount | grep -q "overlay on / "; then
        echo -e "Overlay: ${GREEN}ACTIVE${NC}"
    else
        echo -e "Overlay: ${YELLOW}INACTIVE${NC}"
    fi

    # Check raspi-config overlay setting
    if [[ -f /boot/cmdline.txt ]] && grep -q "boot=overlay" /boot/cmdline.txt; then
        echo -e "Boot config: ${GREEN}ENABLED${NC}"
    else
        echo -e "Boot config: ${YELLOW}DISABLED${NC}"
    fi

    # Show mount status
    echo ""
    echo "Current mounts:"
    mount | grep -E "^/dev|overlay" | head -10
}

enable_overlay() {
    log_info "Enabling read-only overlay filesystem..."

    # Method 1: Use raspi-config if available (Raspberry Pi OS)
    if command -v raspi-config &> /dev/null; then
        log_info "Using raspi-config to enable overlay..."

        # Enable overlay filesystem
        raspi-config nonint enable_overlayfs

        # Make boot partition read-only
        raspi-config nonint enable_bootro

        log_info "Overlay enabled via raspi-config"
        log_warn "Reboot required to activate!"
        return
    fi

    # Method 2: Manual setup for non-Raspberry Pi OS
    log_info "raspi-config not found, performing manual setup..."

    # Install required packages
    apt-get update
    apt-get install -y busybox initramfs-tools overlayroot

    # Configure overlayroot
    if [[ ! -f /etc/overlayroot.conf.bak ]]; then
        cp /etc/overlayroot.conf /etc/overlayroot.conf.bak
    fi

    cat > /etc/overlayroot.conf << 'EOF'
# Enable tmpfs overlay
overlayroot="tmpfs:swap=1,recurse=0"
EOF

    # Update initramfs
    update-initramfs -u

    log_info "Overlay configured"
    log_warn "Reboot required to activate!"
}

disable_overlay() {
    log_info "Disabling read-only overlay filesystem..."

    # Method 1: Use raspi-config if available
    if command -v raspi-config &> /dev/null; then
        log_info "Using raspi-config to disable overlay..."

        # Disable overlay filesystem
        raspi-config nonint disable_overlayfs

        # Make boot partition writable
        raspi-config nonint disable_bootro

        log_info "Overlay disabled via raspi-config"
        log_warn "Reboot required to deactivate!"
        return
    fi

    # Method 2: Manual disable
    log_info "Performing manual disable..."

    if [[ -f /etc/overlayroot.conf.bak ]]; then
        cp /etc/overlayroot.conf.bak /etc/overlayroot.conf
    else
        echo 'overlayroot=""' > /etc/overlayroot.conf
    fi

    update-initramfs -u

    log_info "Overlay disabled"
    log_warn "Reboot required to deactivate!"
}

prepare_for_readonly() {
    log_info "Preparing system for read-only operation..."

    # Disable swap
    log_info "Disabling swap..."
    dphys-swapfile swapoff 2>/dev/null || true
    dphys-swapfile uninstall 2>/dev/null || true
    systemctl disable dphys-swapfile 2>/dev/null || true

    # Disable unnecessary services that write to disk
    log_info "Disabling write-heavy services..."

    # Disable fake-hwclock (writes on shutdown)
    systemctl disable fake-hwclock 2>/dev/null || true

    # Configure journald to use volatile storage
    log_info "Configuring journald for volatile storage..."
    mkdir -p /etc/systemd/journald.conf.d
    cat > /etc/systemd/journald.conf.d/volatile.conf << 'EOF'
[Journal]
Storage=volatile
RuntimeMaxUse=16M
EOF

    # Move frequently written files to tmpfs
    log_info "Configuring tmpfs mounts..."

    # Add tmpfs entries to fstab if not present
    if ! grep -q "tmpfs /var/log" /etc/fstab; then
        cat >> /etc/fstab << 'EOF'

# Tmpfs mounts for read-only operation
tmpfs /var/log tmpfs defaults,noatime,nosuid,mode=0755,size=16m 0 0
tmpfs /var/tmp tmpfs defaults,noatime,nosuid,mode=1777,size=16m 0 0
tmpfs /tmp tmpfs defaults,noatime,nosuid,mode=1777,size=32m 0 0
EOF
    fi

    # Disable apt daily updates
    log_info "Disabling automatic updates..."
    systemctl disable apt-daily.timer 2>/dev/null || true
    systemctl disable apt-daily-upgrade.timer 2>/dev/null || true

    log_info "System prepared for read-only operation"
    echo ""
    echo "Tmpfs will be mounted for:"
    echo "  - /var/log (16MB)"
    echo "  - /var/tmp (16MB)"
    echo "  - /tmp (32MB)"
    echo ""
    echo "Note: Logs will be lost on reboot!"
    echo "Consider setting up remote syslog for persistent logging."
}

usage() {
    echo "Usage: $0 [command]"
    echo ""
    echo "Commands:"
    echo "  status   - Show current overlay status"
    echo "  prepare  - Prepare system for read-only (run first)"
    echo "  enable   - Enable read-only overlay"
    echo "  disable  - Disable read-only overlay"
    echo ""
    echo "Typical workflow:"
    echo "  1. sudo $0 prepare"
    echo "  2. sudo $0 enable"
    echo "  3. sudo reboot"
}

# Main
check_root
check_pi

case "${1:-status}" in
    status)
        show_status
        ;;
    prepare)
        prepare_for_readonly
        ;;
    enable)
        enable_overlay
        ;;
    disable)
        disable_overlay
        ;;
    *)
        usage
        exit 1
        ;;
esac
