# AGENTS.md

Instructions for AI coding agents working with this repository.

## Project Overview

This project provides two methods to connect Tuya BLE plant sensors (SGS01) to Home Assistant when the HA instance has no local Bluetooth hardware.

## Directory Structure

```
├── docs/                    # Architecture and SOPs
├── esphome/                 # Option A: ESP32 BLE proxy configs
├── home-assistant/          # HA automations and dashboard cards
├── pi-fallback/             # Option B: Raspberry Pi implementation
```

## Key Files

- `docs/architecture.md` - System design and data flow diagrams
- `docs/sop.md` - Step-by-step setup procedures
- `esphome/ble-proxy.yaml` - ESPHome configuration for ESP32
- `pi-fallback/ble_poller.py` - Main Python poller script
- `pi-fallback/tuya_ble.py` - Tuya BLE protocol implementation

## Working with This Codebase

### Option A (ESP32 + ESPHome)
- ESPHome YAML configuration in `esphome/`
- No code changes typically needed; just update `substitutions` for new devices

### Option B (Raspberry Pi)
- Python 3.9+ with async/await patterns
- Uses `bleak` for BLE, `paho-mqtt` for MQTT
- Tuya BLE protocol implementation in `tuya_ble.py`

### Sensitive Files (Never Commit)
- `secrets.yaml` - WiFi/API credentials
- `config.yaml` - MQTT credentials and device keys
- Any file containing `local_key`, `device_id`, or passwords

## Code Style

- Python: Follow PEP 8, use type hints where practical
- YAML: 2-space indentation
- Keep scripts compatible with Raspberry Pi Zero W (ARM, limited resources)

## Commit Message Convention

This repository enforces [Conventional Commits](https://www.conventionalcommits.org/) via pre-commit.
All commit messages must follow the format:

```
type(scope): subject
```

Allowed types: `feat`, `fix`, `chore`, `docs`, `refactor`, `ci`, `test`, `style`, `perf`, `revert`

Examples:

```
feat: add MQTT reconnect logic
fix(ble_poller): handle timeout on sensor scan
chore: update pre-commit hook versions
docs: add architecture diagram to README
refactor(tuya_ble): simplify packet parsing
ci: add GitHub Actions lint workflow
```

The `scope` is optional. To activate the commit-msg hook after cloning, run:

```bash
make install-hooks
```

## Testing

```bash
# Option B: Test single poll
sudo /opt/ble-poller/venv/bin/python /opt/ble-poller/ble_poller.py --once

# Scan for BLE devices
sudo /opt/ble-poller/venv/bin/python /opt/ble-poller/ble_poller.py --scan
```
