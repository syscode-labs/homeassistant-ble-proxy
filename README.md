# Home Assistant BLE Proxy

Connect Smart Life SGS01 plant sensors (and other Tuya BLE devices) to Home Assistant running on a VM without Bluetooth hardware.

## Quick Start

**Option A (Recommended):** ESP32 + ESPHome BLE Proxy
- Flash ESP32-C3 with ESPHome
- Install Tuya BLE integration via HACS
- Sensors auto-discover

**Option B (Fallback):** Raspberry Pi + Custom Python
- Pi Zero W with read-only filesystem
- Custom BLE poller publishes to MQTT
- Full control over polling logic

## Documentation

- [Architecture Overview](docs/architecture.md) - How it all works
- [Standard Operating Procedures](docs/sop.md) - Step-by-step setup guides

## Project Structure

```
.
├── docs/
│   ├── architecture.md           # System design and data flow
│   └── sop.md                    # Step-by-step setup procedures
├── esphome/
│   ├── ble-proxy.yaml            # ESPHome BLE proxy configuration
│   └── secrets.yaml.example      # Template for WiFi/API secrets
├── home-assistant/
│   ├── automations/
│   │   └── poke-sgs01.yaml       # Automation to poll SGS01 sensors
│   └── dashboard/
│       ├── plant-card.yaml       # Simple Lovelace cards
│       ├── plant-card-advanced.yaml  # Mushroom + mini-graph cards
│       └── plant-notifications.yaml  # Watering alerts & daily summary
├── pi-fallback/                  # Option B: Raspberry Pi implementation
│   ├── ble_poller.py             # Main polling script
│   ├── tuya_ble.py               # Tuya BLE protocol implementation
│   ├── mqtt_publisher.py         # MQTT with HA Discovery
│   ├── config.yaml.example       # Configuration template
│   ├── requirements.txt          # Python dependencies
│   ├── ble-poller.service        # systemd service unit
│   └── scripts/
│       ├── install.sh            # Installation script
│       └── setup-readonly.sh     # Read-only filesystem setup
└── README.md
```

## Hardware

### Option A
- ESP32-C3 SuperMini (~$3) or ESP32-WROOM (~$5)
- USB power

### Option B
- Raspberry Pi Zero W (~$15)
- MicroSD card (8GB+)
- USB power

## Requirements

- Home Assistant with MQTT broker (Mosquitto)
- Tuya/Smart Life account (for credential extraction)
- WiFi network

## References

- [ESPHome Bluetooth Proxy](https://esphome.io/components/bluetooth_proxy/)
- [Tuya BLE Integration](https://github.com/PlusPlus-ua/ha_tuya_ble)
- [HA Community Discussion](https://community.home-assistant.io/t/smartlife-plant-sensor-sgs01/558491)
