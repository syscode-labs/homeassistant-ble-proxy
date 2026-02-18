# BLE Proxy Architecture for Home Assistant

## Overview

This project connects Smart Life SGS01 plant sensors (and potentially other Tuya BLE devices) to a Home Assistant instance running on an Unraid VM. Since the VM has no Bluetooth hardware, we use remote BLE proxies to bridge the gap.

## Network Topology

```
┌─────────────────────────────────────────────────────────────────┐
│                     Home Network                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────┐         ┌──────────────────────────────────┐  │
│  │  SGS01       │   BLE   │  ESP32-C3 (or Pi fallback)       │  │
│  │  Plant       │◄───────►│                                  │  │
│  │  Sensor      │         │  Option A: ESPHome BLE Proxy     │  │
│  └──────────────┘         │  Option B: Python + bleak        │  │
│                           └───────────────┬──────────────────┘  │
│                                           │ WiFi                │
│                                           ▼                     │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  Home Assistant (Unraid VM)                                │ │
│  │  homeassistant.wind-bearded.ts.net                         │ │
│  │                                                            │ │
│  │  ┌─────────────┐    ┌─────────────┐    ┌────────────────┐  │ │
│  │  │ Mosquitto   │◄───│ Tuya BLE    │    │ MQTT Discovery │  │ │
│  │  │ MQTT Broker │    │ Integration │    │ (fallback)     │  │ │
│  │  └─────────────┘    └─────────────┘    └────────────────┘  │ │
│  └────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

## Implementation Options

### Option A: ESP32 + ESPHome BLE Proxy (Primary)

The ESP32 acts as a "dumb pipe" - it extends Home Assistant's Bluetooth reach over WiFi but doesn't understand the sensor protocol.

```
┌─────────┐     BLE      ┌─────────┐    WiFi/API    ┌──────────────────┐
│  SGS01  │◄────────────►│  ESP32  │◄──────────────►│  Home Assistant  │
│ Sensor  │              │  Proxy  │                │                  │
└─────────┘              └─────────┘                │  ┌────────────┐  │
                          (dumb pipe)               │  │ Tuya BLE   │  │
                                                    │  │ Integration│  │
                                                    │  └────────────┘  │
                                                    │   (does the      │
                                                    │    actual work)  │
                                                    └──────────────────┘
```

**Components:**
- **ESP32**: Runs ESPHome firmware with `bluetooth_proxy` component
- **ESPHome API**: Native encrypted connection to Home Assistant
- **HA Bluetooth Integration**: Aggregates all Bluetooth adapters (local + proxies)
- **Tuya BLE Integration**: HACS custom component that handles Tuya protocol

### Option B: Raspberry Pi + Custom Python (Fallback)

If Option A proves unreliable, the Pi directly communicates with the sensor and publishes to MQTT.

```
┌─────────┐     BLE      ┌─────────────────────────────────────────┐
│  SGS01  │◄────────────►│  Raspberry Pi Zero W                   │
│ Sensor  │              │                                         │
└─────────┘              │  ┌─────────────┐    ┌────────────────┐  │
                         │  │ Python +    │───►│ MQTT Client    │  │
                         │  │ bleak       │    │ (paho-mqtt)    │  │
                         │  └─────────────┘    └───────┬────────┘  │
                         │   (Tuya BLE                 │           │
                         │    protocol)                │           │
                         └─────────────────────────────┼───────────┘
                                                       │ WiFi
                                                       ▼
                         ┌─────────────────────────────────────────┐
                         │  Home Assistant                         │
                         │  ┌─────────────┐    ┌────────────────┐  │
                         │  │ Mosquitto   │───►│ MQTT Discovery │  │
                         │  │ MQTT Broker │    │ (auto-config)  │  │
                         │  └─────────────┘    └────────────────┘  │
                         └─────────────────────────────────────────┘
```

**Components:**
- **Pi Zero W**: Runs Raspberry Pi OS Lite with read-only overlay filesystem
- **Python + bleak**: BLE library for Linux
- **Tuya BLE Protocol**: Custom implementation for device communication
- **MQTT**: Publishes sensor data with HA MQTT Discovery format

## How Bluetooth Proxy Discovery Works

Home Assistant's Bluetooth stack automatically aggregates all available adapters:

```
┌─────────────────────────────────────────────────────────────┐
│  Home Assistant                                             │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  Bluetooth Integration (built-in)                   │    │
│  │                                                     │    │
│  │  Adapters:                                          │    │
│  │   ├─ esp32-proxy-living-room (ESPHome) ← auto-added│    │
│  │   ├─ esp32-proxy-bedroom (ESPHome)     ← auto-added│    │
│  │   └─ (local USB dongle if any)                      │    │
│  │                                                     │    │
│  │  Discovered devices:     ← unified from all adapters│    │
│  │   ├─ SGS01 Plant Sensor (via living-room proxy)    │    │
│  │   └─ Other BLE devices...                          │    │
│  └─────────────────────────────────────────────────────┘    │
│                         │                                   │
│                         ▼                                   │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  Tuya BLE Integration                               │    │
│  │                                                     │    │
│  │  "I see SGS01, let me connect..."                   │    │
│  │   → HA routes connection through living-room proxy  │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

**Discovery Flow:**

1. ESP32 boots, connects to HA via ESPHome API
2. HA Bluetooth integration detects new adapter, adds to pool
3. ESP32 scans BLE, reports discovered devices to HA
4. Tuya BLE integration recognizes SGS01 by device signature
5. When Tuya BLE requests connection, HA routes through the proxy that can see it

**No manual configuration required** - routing is automatic. View adapters at:
Settings → Devices & Services → Bluetooth → (x) adapters

## Design Principles

1. **Same MQTT topics for both options**: Switching A→B requires no HA config changes
2. **Code portability**: ESPHome config identical across ESP32 variants (C3, S3, WROOM)
3. **SD card protection**: Pi fallback uses read-only overlay filesystem
4. **Graceful degradation**: Can run both options simultaneously during testing

## Hardware Requirements

### Option A (per zone)

| Component | Model | Est. Cost |
|-----------|-------|-----------|
| Microcontroller | ESP32-C3 SuperMini | $2-3 |
| Power | USB-C cable + 5V adapter | $3-5 |

### Option B (per zone)

| Component | Model | Est. Cost |
|-----------|-------|-----------|
| SBC | Raspberry Pi Zero W | $15 |
| Storage | MicroSD 8GB+ | $5 |
| Power | Micro USB cable + 5V adapter | $3-5 |

## SGS01 Sensor Notes

The Smart Life SGS01 plant sensor has specific characteristics:

- **Protocol**: Tuya BLE (not passive broadcast)
- **Data points**: Soil moisture, temperature, battery percentage
- **Quirk**: Requires active "poking" to send data updates
- **Workaround**: Periodically write to temperature unit setting to trigger data transmission

## References

- [ESPHome Bluetooth Proxy](https://esphome.io/components/bluetooth_proxy/)
- [Tuya BLE Integration](https://github.com/PlusPlus-ua/ha_tuya_ble)
- [HA Community: SGS01 Discussion](https://community.home-assistant.io/t/smartlife-plant-sensor-sgs01/558491)
- [Read-only Pi Filesystem](https://www.dzombak.com/blog/2024/03/running-a-raspberry-pi-with-a-read-only-root-filesystem/)
