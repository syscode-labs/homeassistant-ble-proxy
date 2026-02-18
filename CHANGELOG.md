# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-02-09

### Added

#### Core Project
- ESP32-based BLE proxy using ESPHome (`esphome/ble-proxy.yaml`) for passive BLE advertisement scanning
- Raspberry Pi fallback BLE poller (`pi-fallback/ble_poller.py`) for environments where ESPHome is not available
- MQTT publisher (`pi-fallback/mqtt_publisher.py`) for publishing BLE device data to Home Assistant
- Tuya BLE protocol support (`pi-fallback/tuya_ble.py`) for decoding proprietary sensor data
- Home Assistant dashboard cards for plant monitoring (`home-assistant/dashboard/`)
- Home Assistant automation for SGS01 sensor pokes (`home-assistant/automations/poke-sgs01.yaml`)
- Systemd service unit for the Raspberry Pi BLE poller (`pi-fallback/ble-poller.service`)
- Installation and setup scripts for Raspberry Pi (`pi-fallback/scripts/`)
- Architecture documentation covering dual ESP32/RPi approach (`docs/architecture.md`)
- Standard Operating Procedure guide (`docs/sop.md`)
- Example configuration files for ESPHome secrets and Pi fallback config

#### Developer Tooling
- MIT License
- `Makefile` with `lint`, `format`, `test`, and `install` targets
- GitHub Actions CI workflow for Python, YAML, and Markdown linting (`.github/workflows/lint.yaml`)
- Dependabot configuration for automated dependency updates (`.github/dependabot.yaml`)
- EditorConfig for consistent editor settings across contributors (`.editorconfig`)
- Ruff configuration for Python linting and formatting (`pi-fallback/ruff.toml`)
- yamllint configuration (`.yamllint.yaml`)
- markdownlint configuration (`.markdownlint.json`)
- pre-commit hooks configuration (`.pre-commit-config.yaml`) integrating Ruff, yamllint, and markdownlint

### Fixed

- Sorted imports in `pi-fallback/ble_poller.py` and `pi-fallback/mqtt_publisher.py` to satisfy Ruff linting
- Removed unused imports in `pi-fallback/tuya_ble.py`
- Renamed unused loop variable in `pi-fallback/tuya_ble.py` to satisfy linting rules
- Relaxed markdownlint line-length rule to allow longer lines in documentation

[Unreleased]: https://github.com/giovanni/homeassistant_ble_proxy/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/giovanni/homeassistant_ble_proxy/releases/tag/v0.1.0
