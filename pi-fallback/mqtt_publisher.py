"""
MQTT Publisher with Home Assistant Discovery

Publishes sensor data to MQTT with automatic Home Assistant entity configuration.
"""

import json
import logging
import ssl
from dataclasses import dataclass
from typing import Optional

import paho.mqtt.client as mqtt

logger = logging.getLogger(__name__)


@dataclass
class MQTTConfig:
    """MQTT connection configuration."""
    host: str
    port: int = 1883
    username: Optional[str] = None
    password: Optional[str] = None
    tls: bool = False
    ca_cert: Optional[str] = None
    discovery_prefix: str = "homeassistant"
    node_id: str = "ble_proxy"


class HADiscoveryPublisher:
    """
    Publishes sensor data to MQTT with Home Assistant Discovery.

    Discovery config is published once per sensor, then state updates
    are published on each poll.
    """

    def __init__(self, config: MQTTConfig):
        self.config = config
        self._client: Optional[mqtt.Client] = None
        self._connected = False
        self._discovery_sent: set = set()

    def connect(self) -> bool:
        """Connect to MQTT broker."""
        try:
            # Use MQTT v5 protocol
            self._client = mqtt.Client(
                client_id=f"{self.config.node_id}_publisher",
                protocol=mqtt.MQTTv5,
            )

            # Set credentials if provided
            if self.config.username:
                self._client.username_pw_set(
                    self.config.username, self.config.password
                )

            # Configure TLS if enabled
            if self.config.tls:
                tls_context = ssl.create_default_context()
                if self.config.ca_cert:
                    tls_context.load_verify_locations(self.config.ca_cert)
                self._client.tls_set_context(tls_context)

            # Set callbacks
            self._client.on_connect = self._on_connect
            self._client.on_disconnect = self._on_disconnect

            # Connect
            logger.info(f"Connecting to MQTT broker {self.config.host}:{self.config.port}")
            self._client.connect(self.config.host, self.config.port, keepalive=60)
            self._client.loop_start()

            # Wait for connection
            import time
            for _ in range(50):  # 5 seconds timeout
                if self._connected:
                    return True
                time.sleep(0.1)

            logger.error("MQTT connection timeout")
            return False

        except Exception as e:
            logger.error(f"MQTT connection error: {e}")
            return False

    def disconnect(self):
        """Disconnect from MQTT broker."""
        if self._client:
            self._client.loop_stop()
            self._client.disconnect()
            self._connected = False

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        """Handle connection callback."""
        if reason_code == 0:
            logger.info("Connected to MQTT broker")
            self._connected = True
        else:
            logger.error(f"MQTT connection failed: {reason_code}")

    def _on_disconnect(self, client, userdata, reason_code, properties=None):
        """Handle disconnection callback."""
        logger.warning(f"Disconnected from MQTT broker: {reason_code}")
        self._connected = False

    def _get_device_info(self, sensor_config: dict) -> dict:
        """Generate device info for HA Discovery."""
        return {
            "identifiers": [sensor_config["unique_id"]],
            "name": sensor_config["name"],
            "manufacturer": "Tuya / Smart Life",
            "model": "SGS01 Plant Sensor",
            "sw_version": "1.0",
            "via_device": self.config.node_id,
        }

    def publish_discovery(self, sensor_config: dict):
        """
        Publish Home Assistant MQTT Discovery configuration.

        This creates entities in HA automatically.
        """
        unique_id = sensor_config["unique_id"]

        if unique_id in self._discovery_sent:
            return

        device_info = self._get_device_info(sensor_config)
        state_topic = f"sgs01/{unique_id}/state"
        availability_topic = f"sgs01/{unique_id}/availability"

        # Define sensors to create
        sensors = [
            {
                "component": "sensor",
                "object_id": "moisture",
                "name": "Soil Moisture",
                "device_class": "moisture",
                "unit_of_measurement": "%",
                "value_template": "{{ value_json.moisture }}",
                "icon": "mdi:water-percent",
            },
            {
                "component": "sensor",
                "object_id": "temperature",
                "name": "Temperature",
                "device_class": "temperature",
                "unit_of_measurement": "°C",
                "value_template": "{{ value_json.temperature }}",
            },
            {
                "component": "sensor",
                "object_id": "battery",
                "name": "Battery",
                "device_class": "battery",
                "unit_of_measurement": "%",
                "value_template": "{{ value_json.battery }}",
                "entity_category": "diagnostic",
            },
        ]

        for sensor in sensors:
            config_topic = (
                f"{self.config.discovery_prefix}/{sensor['component']}/"
                f"{unique_id}_{sensor['object_id']}/config"
            )

            config_payload = {
                "name": sensor["name"],
                "unique_id": f"{unique_id}_{sensor['object_id']}",
                "state_topic": state_topic,
                "availability_topic": availability_topic,
                "payload_available": "online",
                "payload_not_available": "offline",
                "device": device_info,
                "value_template": sensor["value_template"],
            }

            # Add optional fields
            if "device_class" in sensor:
                config_payload["device_class"] = sensor["device_class"]
            if "unit_of_measurement" in sensor:
                config_payload["unit_of_measurement"] = sensor["unit_of_measurement"]
            if "icon" in sensor:
                config_payload["icon"] = sensor["icon"]
            if "entity_category" in sensor:
                config_payload["entity_category"] = sensor["entity_category"]

            # Publish discovery config (retained)
            result = self._client.publish(
                config_topic,
                json.dumps(config_payload),
                qos=1,
                retain=True,
            )

            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                logger.debug(f"Published discovery for {unique_id}_{sensor['object_id']}")
            else:
                logger.error(f"Failed to publish discovery: {result.rc}")

        # Mark as sent
        self._discovery_sent.add(unique_id)
        logger.info(f"Published discovery config for {sensor_config['name']}")

    def publish_state(self, sensor_config: dict, data: dict):
        """
        Publish sensor state to MQTT.

        Args:
            sensor_config: Sensor configuration from config file
            data: Sensor data dictionary (from SensorData.to_dict())
        """
        unique_id = sensor_config["unique_id"]
        state_topic = f"sgs01/{unique_id}/state"

        # Publish state
        result = self._client.publish(
            state_topic,
            json.dumps(data),
            qos=1,
            retain=True,
        )

        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            logger.info(f"Published state for {sensor_config['name']}: {data}")
        else:
            logger.error(f"Failed to publish state: {result.rc}")

    def publish_availability(self, sensor_config: dict, available: bool):
        """Publish sensor availability status."""
        unique_id = sensor_config["unique_id"]
        availability_topic = f"sgs01/{unique_id}/availability"

        payload = "online" if available else "offline"

        self._client.publish(
            availability_topic,
            payload,
            qos=1,
            retain=True,
        )

    def publish_proxy_status(self, online: bool):
        """Publish proxy node availability."""
        # Create a device for the proxy itself
        config_topic = (
            f"{self.config.discovery_prefix}/binary_sensor/"
            f"{self.config.node_id}_status/config"
        )

        state_topic = f"ble_proxy/{self.config.node_id}/status"

        config_payload = {
            "name": "BLE Proxy Status",
            "unique_id": f"{self.config.node_id}_status",
            "state_topic": state_topic,
            "device_class": "connectivity",
            "payload_on": "online",
            "payload_off": "offline",
            "entity_category": "diagnostic",
            "device": {
                "identifiers": [self.config.node_id],
                "name": f"BLE Proxy ({self.config.node_id})",
                "manufacturer": "Custom",
                "model": "Raspberry Pi BLE Proxy",
            },
        }

        # Publish discovery
        self._client.publish(
            config_topic,
            json.dumps(config_payload),
            qos=1,
            retain=True,
        )

        # Publish state
        self._client.publish(
            state_topic,
            "online" if online else "offline",
            qos=1,
            retain=True,
        )
