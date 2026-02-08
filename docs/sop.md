# Standard Operating Procedures

## Table of Contents

1. [Option A: ESP32 + ESPHome Setup](#option-a-esp32--esphome-setup)
2. [Option B: Raspberry Pi Fallback Setup](#option-b-raspberry-pi-fallback-setup)
3. [Tuya Credential Extraction](#tuya-credential-extraction)
4. [Dashboard Setup](#dashboard-setup)
5. [Switching from Option A to Option B](#switching-from-option-a-to-option-b)
6. [Adding Additional Sensors/Zones](#adding-additional-sensorszones)
7. [Troubleshooting](#troubleshooting)

---

## Option A: ESP32 + ESPHome Setup

### Prerequisites

- [ ] ESP32-C3/S3/WROOM board
- [ ] USB-C/Micro-USB cable
- [ ] Home Assistant with ESPHome add-on installed
- [ ] WiFi credentials

### Step 1: Install ESPHome Add-on in Home Assistant

1. Navigate to **Settings → Add-ons → Add-on Store**
2. Search for "ESPHome"
3. Click **Install**
4. After installation, click **Start**
5. Enable **Show in sidebar** for easy access

### Step 2: Create ESPHome Device

1. Open ESPHome from sidebar
2. Click **+ New Device**
3. Name it (e.g., `ble-proxy-living-room`)
4. Select **ESP32-C3** (or your board type)
5. Click **Install** → **Plug into this computer** (first time only)

### Step 3: Configure BLE Proxy

1. In ESPHome, click **Edit** on your device
2. Replace configuration with contents from `../esphome/ble-proxy.yaml`
3. Update `substitutions:` section with your device name
4. Click **Install** → **Wirelessly** (after first flash)

### Step 4: Verify Proxy in Home Assistant

1. Navigate to **Settings → Devices & Services**
2. The ESP32 should auto-discover; click **Configure** if prompted
3. Go to **Settings → Devices & Services → Bluetooth**
4. Verify your proxy appears in the adapters list

### Step 5: Install Tuya BLE Integration

1. Ensure HACS is installed (see [HACS installation](https://hacs.xyz/docs/setup/download))
2. Open **HACS → Integrations**
3. Click **⋮ menu → Custom repositories**
4. Add: `https://github.com/PlusPlus-ua/ha_tuya_ble`
5. Select category: **Integration**
6. Click **Add**
7. Search for "Tuya BLE" and install
8. Restart Home Assistant

### Step 6: Add SGS01 Sensor

1. Ensure sensor is powered on and in range of ESP32 proxy
2. Navigate to **Settings → Devices & Services**
3. Tuya BLE should auto-discover the sensor
4. If not, click **+ Add Integration → Tuya BLE**
5. Enter credentials from [Tuya Credential Extraction](#tuya-credential-extraction)

### Step 7: Create Polling Automation

The SGS01 needs periodic "poking" to send data:

1. Navigate to **Settings → Automations & Scenes**
2. Click **+ Create Automation**
3. Switch to YAML mode
4. Paste contents from `../home-assistant/automations/poke-sgs01.yaml`
5. Adjust entity IDs to match your sensor
6. Save

---

## Option B: Raspberry Pi Fallback Setup

This option provides full control over BLE communication using a custom Python implementation.
Use this if Option A proves unreliable or you need more control over polling behavior.

### Prerequisites

- [ ] Raspberry Pi Zero W (or Pi 3/4)
- [ ] MicroSD card (8GB+)
- [ ] Raspberry Pi Imager
- [ ] Tuya device credentials (see [Tuya Credential Extraction](#tuya-credential-extraction))
- [ ] MQTT broker running (Mosquitto add-on in HA)

### Step 1: Flash Raspberry Pi OS Lite

1. Download [Raspberry Pi Imager](https://www.raspberrypi.com/software/)
2. Select **Raspberry Pi OS Lite (32-bit)** for Zero W, or 64-bit for Pi 3/4
3. Click gear icon (⚙️) for advanced options:
   - Set hostname: `ble-proxy-living-room`
   - Enable SSH with password authentication
   - Set username: `pi` (or your preference)
   - Set password
   - Configure WiFi (SSID and password)
   - Set locale/timezone
4. Select your SD card
5. Click **Write**
6. Insert SD card into Pi and power on

### Step 2: Initial Pi Setup

SSH into the Pi:

```bash
ssh pi@ble-proxy-living-room.local
# Or use IP address if mDNS doesn't work
```

Update the system:

```bash
sudo apt update && sudo apt upgrade -y
```

### Step 3: Copy Project Files

From your workstation, copy the pi-fallback directory to the Pi:

```bash
# From project root on your machine
scp -r pi-fallback pi@ble-proxy-living-room.local:~/
```

### Step 4: Run Installation Script

On the Pi:

```bash
cd ~/pi-fallback/scripts
sudo chmod +x install.sh
sudo ./install.sh
```

This will:
- Install system dependencies (Python, Bluetooth, etc.)
- Create a `ble-poller` service user
- Set up Python virtual environment
- Install the systemd service

### Step 5: Configure the Poller

Edit the configuration file:

```bash
sudo nano /opt/ble-poller/config.yaml
```

Required settings:

```yaml
mqtt:
  host: "homeassistant.wind-bearded.ts.net"  # Your HA address
  port: 1883
  username: "mqtt_user"      # Your MQTT username
  password: "mqtt_password"  # Your MQTT password

sensors:
  - name: "Plant Sensor Living Room"
    mac_address: "AA:BB:CC:DD:EE:FF"  # From BLE scan
    device_id: "your_device_id"        # From Tuya IoT Platform
    local_key: "your_local_key"        # From Tuya IoT Platform
    unique_id: "sgs01_living_room"
```

### Step 6: Scan for Sensors

Find your sensor's MAC address:

```bash
sudo /opt/ble-poller/venv/bin/python /opt/ble-poller/ble_poller.py --scan
```

Example output:
```
Found 1 Tuya device(s):
------------------------------------------------------------
  MAC Address: AA:BB:CC:DD:EE:FF
  Name:        Unknown
  RSSI:        -65 dBm
------------------------------------------------------------
```

Add the MAC address to your config.yaml.

### Step 7: Test the Poller

Run a single poll to verify everything works:

```bash
sudo /opt/ble-poller/venv/bin/python /opt/ble-poller/ble_poller.py --once
```

Check for output like:
```
[INFO] Read from Plant Sensor Living Room: temp=22.5°C, moisture=45%, battery=87%
[INFO] Published state for Plant Sensor Living Room
```

### Step 8: Start the Service

```bash
# Start the service
sudo systemctl start ble-poller

# Check status
sudo systemctl status ble-poller

# View logs
sudo journalctl -u ble-poller -f
```

### Step 9: Verify in Home Assistant

1. Navigate to **Settings → Devices & Services → MQTT**
2. Look for new entities:
   - `sensor.sgs01_living_room_moisture`
   - `sensor.sgs01_living_room_temperature`
   - `sensor.sgs01_living_room_battery`
3. Add to your dashboard

### Step 10: Enable Read-Only Filesystem (Optional but Recommended)

Protect your SD card from wear:

```bash
cd ~/pi-fallback/scripts
sudo chmod +x setup-readonly.sh

# First, prepare the system
sudo ./setup-readonly.sh prepare

# Then enable overlay filesystem
sudo ./setup-readonly.sh enable

# Reboot to activate
sudo reboot
```

**Note:** After enabling read-only mode:
- Changes to config require disabling overlay first
- Logs are stored in RAM and lost on reboot
- Consider setting up remote syslog for persistent logging

To temporarily disable for maintenance:

```bash
sudo ./setup-readonly.sh disable
sudo reboot
# Make changes...
sudo ./setup-readonly.sh enable
sudo reboot
```

---

## Tuya Credential Extraction

The Tuya BLE integration requires device credentials that must be extracted from Tuya Cloud.

### Method 1: Tuya IoT Platform (Recommended)

| Step | Action |
|------|--------|
| 1 | Go to [Tuya IoT Platform](https://iot.tuya.com/) |
| 2 | Create account or sign in |
| 3 | Create a new Cloud Project |
| 4 | Select your data center region (must match Smart Life app) |
| 5 | Go to **Cloud → Link Tuya App Account** |
| 6 | Scan QR code with Smart Life app to link |
| 7 | Navigate to **Devices → All Devices** |
| 8 | Find your SGS01 sensor |
| 9 | Copy: `device_id`, `local_key`, `uuid`, `product_id` |

### Method 2: tuya-cli (Alternative)

```bash
# Install Node.js if not present
# Then install tuya-cli
npm install -g @tuyapi/cli

# Follow prompts to extract credentials
tuya-cli wizard
```

### Storing Credentials

Store extracted credentials in Home Assistant secrets:

```yaml
# secrets.yaml
tuya_device_id: "your_device_id"
tuya_local_key: "your_local_key"
```

---

## Dashboard Setup

Once sensors are working, add them to your Home Assistant dashboard.

### Simple Cards (No custom components)

1. Navigate to your dashboard
2. Click **Edit** (pencil icon) → **+ Add Card**
3. Choose **Manual** card
4. Paste contents from `../home-assistant/dashboard/plant-card.yaml`
5. Update entity IDs to match your sensors
6. Save

### Advanced Cards (Recommended)

For a nicer look with graphs, install these HACS frontend cards first:

| Card | Purpose |
|------|---------|
| [mushroom-cards](https://github.com/piitaya/lovelace-mushroom) | Modern UI components |
| [mini-graph-card](https://github.com/kalkih/mini-graph-card) | Historical graphs |

**Installation:**

1. Open HACS → Frontend
2. Search for "Mushroom" → Install
3. Search for "Mini Graph Card" → Install
4. Refresh browser (Ctrl+F5)

**Add the card:**

1. Edit dashboard → **+ Add Card** → **Manual**
2. Paste contents from `../home-assistant/dashboard/plant-card-advanced.yaml`
3. Update entity IDs
4. Save

### Notification Automations

Set up alerts for low moisture, low battery, and daily summaries:

1. Navigate to **Settings → Automations & Scenes**
2. Click **+ Create Automation** → **Create new automation**
3. Click **⋮ menu → Edit in YAML**
4. Paste automations from `../home-assistant/dashboard/plant-notifications.yaml`
5. Update entity IDs and notification service
6. Save

**Available automations:**

| Automation | Trigger |
|------------|---------|
| Plant Needs Water | Moisture below 25% for 30 min |
| Low Battery Alert | Battery below 20% |
| Daily Plant Summary | 9:00 AM daily |
| Sensor Offline | Unavailable for 2 hours |

---

## Switching from Option A to Option B

If Option A (ESP32 + Tuya BLE integration) proves unreliable:

| Step | Action |
|------|--------|
| 1 | Complete [Option B setup](#option-b-raspberry-pi-fallback-setup) |
| 2 | Verify Pi is publishing to MQTT |
| 3 | Check HA auto-discovers entities via MQTT Discovery |
| 4 | Disable or remove Tuya BLE integration |
| 5 | (Optional) Repurpose ESP32 for other uses or keep as backup |

**Note:** Both options use the same MQTT topics, so HA entities remain consistent.

---

## Adding Additional Sensors/Zones

### Option A: Add Another ESP32 Proxy

1. Flash new ESP32 with ESPHome
2. Update `substitutions:` with unique name (e.g., `ble-proxy-bedroom`)
3. Deploy configuration
4. New proxy auto-registers with HA Bluetooth integration
5. Sensors in range of new proxy are automatically discovered

### Option B: Add Another Pi

1. Flash new Pi with same base image
2. Update hostname and sensor configuration
3. Deploy Python poller script
4. Configure to publish to same MQTT broker

### Adding More SGS01 Sensors

For Option A:
- Sensors auto-discover if in range of any proxy
- No additional configuration needed

For Option B:
- Add sensor MAC address and credentials to configuration
- Restart poller service

---

## Troubleshooting

### Option A: ESP32 Issues

#### ESP32 Proxy Not Appearing in HA

| Check | Solution |
|-------|----------|
| ESP32 connected to WiFi? | Check ESPHome logs for connection status |
| API connection working? | Verify `api:` section has correct encryption key |
| Firewall blocking? | Ensure port 6053 (ESPHome API) is open |

#### Sensor Not Discovered

| Check | Solution |
|-------|----------|
| Sensor powered on? | Replace batteries if needed |
| In BLE range? | Move sensor closer to proxy (~10m max) |
| Proxy scanning? | Check ESPHome logs for BLE scan activity |

#### Sensor Shows "Unavailable"

| Check | Solution |
|-------|----------|
| Tuya credentials correct? | Re-extract from Tuya IoT Platform |
| Polling automation running? | Check automation traces |
| Connection slots exhausted? | Reduce other BLE devices or add proxy |

#### Data Not Updating

The SGS01 requires active polling:

1. Verify polling automation is enabled
2. Check automation traces for errors
3. Manually trigger automation to test
4. Review Tuya BLE integration logs

### Option B: Raspberry Pi Issues

#### Service Won't Start

```bash
# Check service status
sudo systemctl status ble-poller

# View detailed logs
sudo journalctl -u ble-poller -n 50 --no-pager
```

| Issue | Solution |
|-------|----------|
| "Permission denied" | Verify user is in bluetooth group: `sudo usermod -a -G bluetooth ble-poller` |
| "No such file" | Check paths in service file match installation |
| "Module not found" | Reinstall dependencies: `sudo /opt/ble-poller/venv/bin/pip install -r /opt/ble-poller/requirements.txt` |

#### Bluetooth Not Working

```bash
# Check Bluetooth status
sudo systemctl status bluetooth
hciconfig -a

# Restart Bluetooth
sudo systemctl restart bluetooth

# Scan for devices manually
sudo hcitool lescan
```

| Issue | Solution |
|-------|----------|
| "Device not found" | Run `sudo hciconfig hci0 up` |
| No devices in scan | Check sensor batteries, move closer |
| "Operation not permitted" | Add CAP_NET_RAW capability or run as root for testing |

#### Connection Failures

| Issue | Solution |
|-------|----------|
| "Connection timeout" | Increase `connect_timeout_seconds` in config |
| "Device disconnected" | Sensor may be connected elsewhere; reset sensor |
| "Encryption failed" | Verify `local_key` is correct |

#### MQTT Issues

```bash
# Test MQTT connection manually
mosquitto_pub -h homeassistant.local -u user -P pass -t test -m "hello"
```

| Issue | Solution |
|-------|----------|
| "Connection refused" | Check MQTT host/port in config |
| "Not authorized" | Verify MQTT username/password |
| "No route to host" | Check network connectivity, firewall |

#### Read-Only Filesystem Issues

```bash
# Check overlay status
sudo /path/to/setup-readonly.sh status

# Temporarily disable for changes
sudo /path/to/setup-readonly.sh disable
sudo reboot
```

| Issue | Solution |
|-------|----------|
| Can't edit config | Disable overlay, reboot, edit, re-enable |
| Logs disappearing | Expected with overlay; use remote syslog |
| Changes not persisting | Verify overlay is disabled before editing |

### View Logs

```bash
# ESPHome device logs (from HA)
# ESPHome sidebar → device → Logs

# Home Assistant logs
# Settings → System → Logs → Filter by "tuya_ble"

# Pi fallback logs (SSH to Pi)
sudo journalctl -u ble-poller -f

# Bluetooth daemon logs
sudo journalctl -u bluetooth -f

# Full system logs
sudo journalctl -f
```

### Debug Mode

For detailed debugging, edit config.yaml:

```yaml
logging:
  level: "DEBUG"
```

Then restart the service:

```bash
sudo systemctl restart ble-poller
sudo journalctl -u ble-poller -f
```
