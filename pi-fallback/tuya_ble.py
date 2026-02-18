"""
Tuya BLE Protocol Implementation

This module handles communication with Tuya BLE devices like the SGS01 plant sensor.
Based on reverse-engineering of the Tuya BLE protocol.

References:
- https://github.com/PlusPlus-ua/ha_tuya_ble
- https://github.com/redphx/tuya-local-key-extractor
"""

import asyncio
import hashlib
import logging
import struct
from dataclasses import dataclass
from enum import IntEnum
from typing import Optional

from bleak import BleakClient, BleakScanner
from bleak.exc import BleakError
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

logger = logging.getLogger(__name__)


# Tuya BLE UUIDs
TUYA_SERVICE_UUID = "00001910-0000-1000-8000-00805f9b34fb"
TUYA_CHAR_WRITE_UUID = "00002b11-0000-1000-8000-00805f9b34fb"
TUYA_CHAR_NOTIFY_UUID = "00002b10-0000-1000-8000-00805f9b34fb"


class TuyaCommand(IntEnum):
    """Tuya BLE command codes."""
    PAIR_REQ = 0x01
    PAIR_RESP = 0x02
    DEVICE_INFO_REQ = 0x03
    DEVICE_INFO_RESP = 0x04
    DP_QUERY = 0x08
    DP_REPORT = 0x07
    DP_WRITE = 0x06
    TIME_SYNC = 0x0D


class DPType(IntEnum):
    """Tuya Data Point types."""
    RAW = 0x00
    BOOL = 0x01
    VALUE = 0x02  # Integer
    STRING = 0x03
    ENUM = 0x04
    BITMAP = 0x05


# SGS01 Data Point mappings
# These may vary by firmware version
SGS01_DP_MAPPING = {
    3: ("temperature", DPType.VALUE, lambda x: x / 10.0),  # Temperature in 0.1°C
    4: ("moisture", DPType.VALUE, lambda x: x),  # Moisture percentage
    15: ("battery", DPType.VALUE, lambda x: x),  # Battery percentage
    14: ("battery_state", DPType.ENUM, lambda x: ["low", "medium", "high"][x] if x < 3 else "unknown"),
    9: ("temp_unit", DPType.ENUM, lambda x: "celsius" if x == 0 else "fahrenheit"),
}


@dataclass
class SensorData:
    """Parsed sensor data from SGS01."""
    temperature: Optional[float] = None
    moisture: Optional[int] = None
    battery: Optional[int] = None
    battery_state: Optional[str] = None
    temp_unit: Optional[str] = None
    raw_dps: dict = None

    def __post_init__(self):
        if self.raw_dps is None:
            self.raw_dps = {}

    def to_dict(self) -> dict:
        """Convert to dictionary for MQTT publishing."""
        result = {}
        if self.temperature is not None:
            result["temperature"] = round(self.temperature, 1)
        if self.moisture is not None:
            result["moisture"] = self.moisture
        if self.battery is not None:
            result["battery"] = self.battery
        if self.battery_state is not None:
            result["battery_state"] = self.battery_state
        return result


class TuyaBLEDevice:
    """
    Handles BLE communication with a Tuya device.
    """

    def __init__(
        self,
        mac_address: str,
        device_id: str,
        local_key: str,
        uuid: str = None,
        product_id: str = None,
        connect_timeout: float = 30.0,
    ):
        self.mac_address = mac_address.upper()
        self.device_id = device_id
        self.local_key = local_key
        self.uuid = uuid or device_id
        self.product_id = product_id
        self.connect_timeout = connect_timeout

        self._client: Optional[BleakClient] = None
        self._session_key: Optional[bytes] = None
        self._seq_num: int = 0
        self._response_event = asyncio.Event()
        self._response_data: Optional[bytes] = None
        self._received_dps: dict = {}

    def _get_key(self) -> bytes:
        """Get encryption key (first 16 bytes of local_key MD5)."""
        if len(self.local_key) == 16:
            return self.local_key.encode()
        # Hash longer keys
        return hashlib.md5(self.local_key.encode()).digest()

    def _encrypt(self, data: bytes) -> bytes:
        """Encrypt data using AES-128-ECB."""
        key = self._session_key or self._get_key()
        # Pad to 16-byte boundary
        padding_len = 16 - (len(data) % 16)
        padded_data = data + bytes([padding_len] * padding_len)

        cipher = Cipher(algorithms.AES(key), modes.ECB(), backend=default_backend())
        encryptor = cipher.encryptor()
        return encryptor.update(padded_data) + encryptor.finalize()

    def _decrypt(self, data: bytes) -> bytes:
        """Decrypt data using AES-128-ECB."""
        key = self._session_key or self._get_key()

        cipher = Cipher(algorithms.AES(key), modes.ECB(), backend=default_backend())
        decryptor = cipher.decryptor()
        decrypted = decryptor.update(data) + decryptor.finalize()

        # Remove PKCS7 padding
        padding_len = decrypted[-1]
        if padding_len == 0 or padding_len > 16:
            raise ValueError(f"Invalid PKCS7 padding length: {padding_len}")
        return decrypted[:-padding_len]

    def _build_packet(self, command: int, data: bytes = b"") -> bytes:
        """Build a Tuya BLE packet."""
        self._seq_num = (self._seq_num + 1) & 0xFFFF

        # Packet format: [seq_num:2][cmd:1][length:2][data:n][crc:2]
        header = struct.pack(">HBH", self._seq_num, command, len(data))
        packet = header + data

        # Calculate CRC16
        crc = self._crc16(packet)
        packet += struct.pack(">H", crc)

        return packet

    def _crc16(self, data: bytes) -> int:
        """Calculate CRC16-CCITT."""
        crc = 0xFFFF
        for byte in data:
            crc ^= byte << 8
            for _ in range(8):
                if crc & 0x8000:
                    crc = (crc << 1) ^ 0x1021
                else:
                    crc <<= 1
                crc &= 0xFFFF
        return crc

    def _parse_dps(self, data: bytes) -> dict:
        """Parse data points from response."""
        dps = {}
        offset = 0

        while offset < len(data):
            if offset + 4 > len(data):
                break

            dp_id = data[offset]
            dp_type = data[offset + 1]
            dp_len = struct.unpack(">H", data[offset + 2:offset + 4])[0]
            offset += 4

            if offset + dp_len > len(data):
                break

            dp_data = data[offset:offset + dp_len]
            offset += dp_len

            # Parse value based on type
            if dp_type == DPType.BOOL:
                value = bool(dp_data[0]) if dp_data else False
            elif dp_type == DPType.VALUE:
                value = struct.unpack(">i", dp_data.rjust(4, b'\x00')[:4])[0]
            elif dp_type == DPType.STRING:
                value = dp_data.decode("utf-8", errors="replace")
            elif dp_type == DPType.ENUM:
                value = dp_data[0] if dp_data else 0
            else:
                value = dp_data.hex()

            dps[dp_id] = value
            logger.debug(f"DP {dp_id}: type={dp_type}, value={value}")

        return dps

    async def _notification_handler(self, sender, data: bytes):
        """Handle incoming BLE notifications."""
        logger.debug(f"Received notification: {data.hex()}")

        try:
            # Parse packet header
            if len(data) < 7:
                return

            seq_num, cmd, length = struct.unpack(">HBH", data[:5])
            payload = data[5:5 + length]

            if cmd == TuyaCommand.PAIR_RESP:
                # Pairing response contains session key material
                self._response_data = payload
                self._response_event.set()

            elif cmd == TuyaCommand.DP_REPORT:
                # Data point report
                if self._session_key and len(payload) >= 16:
                    decrypted = self._decrypt(payload)
                    dps = self._parse_dps(decrypted)
                    self._received_dps.update(dps)
                else:
                    dps = self._parse_dps(payload)
                    self._received_dps.update(dps)
                self._response_event.set()

            elif cmd == TuyaCommand.DEVICE_INFO_RESP:
                self._response_data = payload
                self._response_event.set()

        except Exception as e:
            logger.error(f"Error handling notification: {e}")

    async def connect(self) -> bool:
        """Connect to the device and perform pairing."""
        try:
            logger.info(f"Connecting to {self.mac_address}...")

            # Find device first
            device = await BleakScanner.find_device_by_address(
                self.mac_address, timeout=10.0
            )
            if not device:
                logger.error(f"Device {self.mac_address} not found")
                return False

            self._client = BleakClient(device, timeout=self.connect_timeout)
            await self._client.connect()

            if not self._client.is_connected:
                logger.error("Failed to connect")
                return False

            logger.info("Connected, starting notifications...")

            # Start notifications
            await self._client.start_notify(
                TUYA_CHAR_NOTIFY_UUID, self._notification_handler
            )

            # Perform pairing
            await self._pair()

            logger.info("Pairing complete")
            return True

        except BleakError as e:
            logger.error(f"BLE error: {e}")
            return False
        except Exception as e:
            logger.error(f"Connection error: {e}")
            return False

    async def _pair(self):
        """Perform Tuya BLE pairing handshake."""
        # Generate random session data
        import os
        rand_data = os.urandom(6)

        # Build pairing request
        # Format varies by device, this is a common format
        pair_data = (
            self.uuid.encode()[:16].ljust(16, b'\x00') +
            self._get_key() +
            rand_data
        )

        encrypted = self._encrypt(pair_data)
        packet = self._build_packet(TuyaCommand.PAIR_REQ, encrypted)

        self._response_event.clear()
        await self._client.write_gatt_char(TUYA_CHAR_WRITE_UUID, packet)

        # Wait for response
        try:
            await asyncio.wait_for(self._response_event.wait(), timeout=10.0)
        except asyncio.TimeoutError:
            logger.warning("Pairing response timeout, continuing anyway...")

        # Derive session key if response received
        if self._response_data:
            try:
                decrypted = self._decrypt(self._response_data)
                if len(decrypted) >= 16:
                    self._session_key = decrypted[:16]
                    logger.debug("Session key established")
            except Exception as e:
                logger.warning(f"Could not derive session key: {e}")

    async def disconnect(self):
        """Disconnect from the device."""
        if self._client and self._client.is_connected:
            try:
                await self._client.disconnect()
            except Exception as e:
                logger.warning(f"Disconnect error: {e}")
        self._client = None
        self._session_key = None

    async def read_sensors(self) -> Optional[SensorData]:
        """Read sensor data from the device."""
        if not self._client or not self._client.is_connected:
            logger.error("Not connected")
            return None

        try:
            self._received_dps.clear()
            self._response_event.clear()

            # Query all data points
            packet = self._build_packet(TuyaCommand.DP_QUERY, b"\x00")
            await self._client.write_gatt_char(TUYA_CHAR_WRITE_UUID, packet)

            # Wait for response
            try:
                await asyncio.wait_for(self._response_event.wait(), timeout=10.0)
            except asyncio.TimeoutError:
                logger.warning("Query response timeout")

            # If no DPs received, try triggering by writing temp unit
            if not self._received_dps:
                self._response_event.clear()
                await self._trigger_update()
                if not self._received_dps:
                    # Clear stale signal from _trigger_update's DP_WRITE ack before
                    # waiting for the actual DP_REPORT notification
                    self._response_event.clear()
                    try:
                        await asyncio.wait_for(self._response_event.wait(), timeout=5.0)
                    except asyncio.TimeoutError:
                        logger.warning("No DPs received after trigger update")

            # Parse received DPs into SensorData
            return self._parse_sensor_data()

        except Exception as e:
            logger.error(f"Error reading sensors: {e}")
            return None

    async def _trigger_update(self):
        """Trigger sensor to send data by writing temperature unit."""
        if not self._client or not self._client.is_connected:
            logger.error("Device disconnected, cannot trigger update")
            return

        # Write DP 9 (temp_unit) = 0 (celsius)
        dp_data = struct.pack(">BBHB", 9, DPType.ENUM, 1, 0)

        if self._session_key:
            encrypted = self._encrypt(dp_data)
            packet = self._build_packet(TuyaCommand.DP_WRITE, encrypted)
        else:
            packet = self._build_packet(TuyaCommand.DP_WRITE, dp_data)

        self._response_event.clear()
        await self._client.write_gatt_char(TUYA_CHAR_WRITE_UUID, packet)

        try:
            await asyncio.wait_for(self._response_event.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            pass

    def _parse_sensor_data(self) -> SensorData:
        """Parse received DPs into SensorData object."""
        data = SensorData(raw_dps=self._received_dps.copy())

        for dp_id, (name, _dp_type, transform) in SGS01_DP_MAPPING.items():
            if dp_id in self._received_dps:
                try:
                    value = transform(self._received_dps[dp_id])
                    setattr(data, name, value)
                except Exception as e:
                    logger.warning(f"Error parsing DP {dp_id}: {e}")

        return data


async def scan_for_tuya_devices(timeout: float = 10.0) -> list:
    """Scan for Tuya BLE devices."""
    logger.info(f"Scanning for Tuya BLE devices ({timeout}s)...")

    devices = []

    def detection_callback(device, advertisement_data):
        # Check for Tuya service UUID
        if TUYA_SERVICE_UUID.lower() in [
            str(uuid).lower() for uuid in advertisement_data.service_uuids
        ]:
            devices.append({
                "mac": device.address,
                "name": device.name or "Unknown",
                "rssi": advertisement_data.rssi,
            })
            logger.info(f"Found Tuya device: {device.address} ({device.name})")

    scanner = BleakScanner(detection_callback)
    await scanner.start()
    await asyncio.sleep(timeout)
    await scanner.stop()

    return devices
