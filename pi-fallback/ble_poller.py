#!/usr/bin/env python3
"""
BLE Poller - Main entry point

Polls Tuya BLE sensors (SGS01) and publishes data to MQTT for Home Assistant.

Usage:
    python ble_poller.py [--config CONFIG_FILE] [--scan] [--once]

Options:
    --config    Path to config file (default: config.yaml)
    --scan      Scan for Tuya BLE devices and exit
    --once      Run one poll cycle and exit (for testing)
"""

import argparse
import asyncio
import logging
import signal
import sys
from pathlib import Path
from typing import Optional

import yaml

from mqtt_publisher import HADiscoveryPublisher, MQTTConfig
from tuya_ble import SensorData, TuyaBLEDevice, scan_for_tuya_devices

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ble_poller")


class BLEPoller:
    """
    Main poller class that coordinates BLE reading and MQTT publishing.
    """

    def __init__(self, config_path: str = "config.yaml"):
        self.config_path = Path(config_path)
        self.config: dict = {}
        self.mqtt: Optional[HADiscoveryPublisher] = None
        self._running = False
        self._shutdown_event = asyncio.Event()

    def load_config(self) -> bool:
        """Load configuration from YAML file."""
        try:
            if not self.config_path.exists():
                logger.error(f"Config file not found: {self.config_path}")
                return False

            with open(self.config_path) as f:
                self.config = yaml.safe_load(f)

            # Validate required sections
            required = ["mqtt", "sensors"]
            for section in required:
                if section not in self.config:
                    logger.error(f"Missing required config section: {section}")
                    return False

            # Validate required sensor keys early to catch config errors at startup
            required_sensor_keys = ["mac_address", "device_id", "local_key"]
            for i, sensor in enumerate(self.config.get("sensors", [])):
                for key in required_sensor_keys:
                    if key not in sensor:
                        logger.error(
                            f"Sensor {i} ('{sensor.get('name', 'unnamed')}') "
                            f"missing required key: '{key}'"
                        )
                        return False

            # Set logging level
            log_level = self.config.get("logging", {}).get("level", "INFO")
            logging.getLogger().setLevel(getattr(logging, log_level.upper()))

            logger.info(f"Loaded config from {self.config_path}")
            logger.info(f"Found {len(self.config['sensors'])} sensor(s)")
            return True

        except yaml.YAMLError as e:
            logger.error(f"YAML parse error: {e}")
            return False
        except Exception as e:
            logger.error(f"Config load error: {e}")
            return False

    async def connect_mqtt(self) -> bool:
        """Initialize and connect MQTT publisher."""
        mqtt_config = self.config["mqtt"]
        ha_config = self.config.get("homeassistant", {})

        config = MQTTConfig(
            host=mqtt_config["host"],
            port=mqtt_config.get("port", 1883),
            username=mqtt_config.get("username"),
            password=mqtt_config.get("password"),
            tls=mqtt_config.get("tls", False),
            ca_cert=mqtt_config.get("ca_cert"),
            discovery_prefix=ha_config.get("discovery_prefix", "homeassistant"),
            node_id=ha_config.get("node_id", "ble_proxy"),
        )

        self.mqtt = HADiscoveryPublisher(config)
        return await self.mqtt.connect()

    async def poll_sensor(self, sensor_config: dict) -> Optional[SensorData]:
        """
        Poll a single sensor and return data.

        Args:
            sensor_config: Sensor configuration dictionary

        Returns:
            SensorData if successful, None otherwise
        """
        polling_config = self.config.get("polling", {})

        device = TuyaBLEDevice(
            mac_address=sensor_config["mac_address"],
            device_id=sensor_config["device_id"],
            local_key=sensor_config["local_key"],
            uuid=sensor_config.get("uuid"),
            product_id=sensor_config.get("product_id"),
            connect_timeout=polling_config.get("connect_timeout_seconds", 30),
        )

        try:
            # Connect to device
            if not await device.connect():
                logger.error(f"Failed to connect to {sensor_config['name']}")
                return None

            # Read sensors
            data = await device.read_sensors()

            if data:
                logger.info(
                    f"Read from {sensor_config['name']}: "
                    f"temp={data.temperature}°C, moisture={data.moisture}%, "
                    f"battery={data.battery}%"
                )
            else:
                logger.warning(f"No data from {sensor_config['name']}")

            return data

        finally:
            await device.disconnect()

    async def poll_all_sensors(self):
        """Poll all configured sensors."""
        polling_config = self.config.get("polling", {})
        retry_attempts = polling_config.get("retry_attempts", 3)
        retry_delay = polling_config.get("retry_delay_seconds", 30)

        for sensor_config in self.config["sensors"]:
            # Ensure discovery is published
            self.mqtt.publish_discovery(sensor_config)

            # Try polling with retries
            data = None
            for attempt in range(retry_attempts):
                try:
                    data = await self.poll_sensor(sensor_config)
                    if data:
                        break
                except Exception as e:
                    logger.error(
                        f"Poll attempt {attempt + 1}/{retry_attempts} failed "
                        f"for {sensor_config['name']}: {e}"
                    )

                if attempt < retry_attempts - 1:
                    logger.info(f"Retrying in {retry_delay}s...")
                    await asyncio.sleep(retry_delay)

            # Publish results
            if data:
                self.mqtt.publish_availability(sensor_config, True)
                self.mqtt.publish_state(sensor_config, data.to_dict())
            else:
                logger.error(f"All attempts failed for {sensor_config['name']}")
                self.mqtt.publish_availability(sensor_config, False)

            # Brief delay between sensors to avoid BLE congestion
            await asyncio.sleep(2)

    async def run(self, once: bool = False):
        """
        Main polling loop.

        Args:
            once: If True, run one poll cycle and exit
        """
        self._running = True
        polling_config = self.config.get("polling", {})
        interval = polling_config.get("interval_seconds", 900)

        # Publish proxy online status
        self.mqtt.publish_proxy_status(True)

        logger.info(f"Starting polling loop (interval: {interval}s)")

        try:
            while self._running:
                await self.poll_all_sensors()

                if once:
                    logger.info("Single poll complete, exiting")
                    break

                # Wait for next poll or shutdown
                logger.info(f"Next poll in {interval}s")
                try:
                    await asyncio.wait_for(
                        self._shutdown_event.wait(),
                        timeout=interval,
                    )
                    # Shutdown requested
                    break
                except asyncio.TimeoutError:
                    # Normal timeout, continue polling
                    pass

        finally:
            # Publish offline status on shutdown
            self.mqtt.publish_proxy_status(False)
            self._running = False

    def shutdown(self):
        """Signal shutdown."""
        logger.info("Shutdown requested")
        self._running = False
        self._shutdown_event.set()


async def scan_devices():
    """Scan for Tuya BLE devices and print results."""
    print("Scanning for Tuya BLE devices...")
    print("Make sure your sensors are powered on and in range.\n")

    devices = await scan_for_tuya_devices(timeout=15.0)

    if devices:
        print(f"\nFound {len(devices)} Tuya device(s):\n")
        print("-" * 60)
        for device in devices:
            print(f"  MAC Address: {device['mac']}")
            print(f"  Name:        {device['name']}")
            print(f"  RSSI:        {device['rssi']} dBm")
            print("-" * 60)
        print("\nAdd these MAC addresses to your config.yaml")
    else:
        print("\nNo Tuya devices found.")
        print("Tips:")
        print("  - Make sure Bluetooth is enabled: sudo systemctl start bluetooth")
        print("  - Ensure sensors have batteries and are within range")
        print("  - Try moving closer to the sensor")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="BLE Poller for Tuya SGS01 Plant Sensors"
    )
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to config file (default: config.yaml)",
    )
    parser.add_argument(
        "--scan",
        action="store_true",
        help="Scan for Tuya BLE devices and exit",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run one poll cycle and exit",
    )
    args = parser.parse_args()

    # Handle scan mode
    if args.scan:
        asyncio.run(scan_devices())
        return 0

    # Initialize poller
    poller = BLEPoller(args.config)

    # Load config (synchronous)
    if not poller.load_config():
        return 1

    # Setup signal handlers
    def signal_handler(sig, frame):
        poller.shutdown()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    async def _run():
        if not await poller.connect_mqtt():
            logger.error("Failed to connect to MQTT broker")
            return 1
        try:
            await poller.run(once=args.once)
        except KeyboardInterrupt:
            pass
        finally:
            if poller.mqtt:
                poller.mqtt.disconnect()
        return 0

    return asyncio.run(_run())


if __name__ == "__main__":
    sys.exit(main())
