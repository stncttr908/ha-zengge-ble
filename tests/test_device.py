#!/usr/bin/env python3
"""Async unit tests for ZenggeLampDevice client with mock BleakClient."""

import asyncio
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from bleak.backends.device import BLEDevice

from custom_components.zengge_ble.const import NOTIFY_UUID, WRITE_UUID
from custom_components.zengge_ble.zengge_protocol import (
    LowerTransportLayerEncoder,
    UpperTransportLayer,
    ZenggeDeviceStatus,
    ZenggeLampDevice,
)


class TestZenggeLampDevice(unittest.IsolatedAsyncioTestCase):
    """Test async device controller operations."""

    def setUp(self):
        self.ble_device = BLEDevice("AA:BB:CC:DD:EE:FF", "IOTBT537", {})
        self.device = ZenggeLampDevice(ble_device=self.ble_device)

    def test_initial_state(self):
        self.assertEqual(self.device.address, "AA:BB:CC:DD:EE:FF")
        self.assertEqual(self.device.name, "IOTBT537")
        self.assertFalse(self.device.is_connected)
        self.assertIsNone(self.device.status)

    def test_set_ble_device(self):
        new_ble_device = BLEDevice("11:22:33:44:55:66", "IOTBT999", {})
        self.device.set_ble_device(new_ble_device)
        self.assertEqual(self.device.address, "11:22:33:44:55:66")
        self.assertEqual(self.device.name, "IOTBT999")

    @patch("custom_components.zengge_ble.zengge_protocol.BleakClient")
    async def test_connect_and_disconnect(self, mock_bleak_client_cls):
        mock_client = MagicMock()
        mock_client.is_connected = True
        mock_client.connect = AsyncMock(return_value=True)
        mock_client.start_notify = AsyncMock()
        mock_client.stop_notify = AsyncMock()
        mock_client.disconnect = AsyncMock()
        mock_bleak_client_cls.return_value = mock_client

        connected = await self.device.connect()
        self.assertTrue(connected)
        self.assertTrue(self.device.is_connected)
        mock_client.connect.assert_awaited_once()
        mock_client.start_notify.assert_awaited_once_with(NOTIFY_UUID, self.device._on_notification)

        await self.device.disconnect()
        self.assertFalse(self.device.is_connected)
        mock_client.disconnect.assert_awaited_once()

    @patch("custom_components.zengge_ble.zengge_protocol.BleakClient")
    async def test_send_command_dispatches_write_gatt(self, mock_bleak_client_cls):
        mock_client = MagicMock()
        mock_client.is_connected = True
        mock_client.connect = AsyncMock(return_value=True)
        mock_client.start_notify = AsyncMock()
        mock_client.write_gatt_char = AsyncMock()
        mock_bleak_client_cls.return_value = mock_client

        await self.device.connect()
        await self.device.power_on()

        mock_client.write_gatt_char.assert_awaited_once()
        write_args = mock_client.write_gatt_char.call_args
        self.assertEqual(write_args[0][0], WRITE_UUID)
        self.assertFalse(write_args[1]["response"])
        # Inner payload for power on is 71 23
        self.assertTrue(write_args[0][1].endswith(bytes([0x71, 0x23])))

    @patch("custom_components.zengge_ble.zengge_protocol.BleakClient")
    async def test_notification_callback_and_response_waiting(self, mock_bleak_client_cls):
        mock_client = MagicMock()
        mock_client.is_connected = True
        mock_client.connect = AsyncMock(return_value=True)
        mock_client.start_notify = AsyncMock()
        mock_client.write_gatt_char = AsyncMock()
        mock_bleak_client_cls.return_value = mock_client

        received_statuses = []

        def on_status(status: ZenggeDeviceStatus):
            received_statuses.append(status)

        unregister = self.device.register_status_callback(on_status)
        await self.device.connect()

        # Simulate incoming GATT notification on 0xFF02
        json_payload = json.dumps({"code": 0, "payload": "EA8100000E0A23610240F0006464000000000000000000000000"}).encode("utf-8")
        upper = UpperTransportLayer(seq=0x15, cmd_id=0x0C, payload=json_payload)
        ntf_frames = LowerTransportLayerEncoder.generate(upper)
        # Set ctrl byte to 0x04 (JSON type)
        first_frame = bytearray(ntf_frames[0])
        first_frame[0] = 0x04

        self.device._on_notification(0, first_frame)

        self.assertEqual(len(received_statuses), 1)
        self.assertTrue(received_statuses[0].power)
        self.assertEqual(received_statuses[0].hue, 0)
        self.assertEqual(self.device.status, received_statuses[0])

        unregister()
        self.device._on_notification(0, first_frame)
        # Should not increase since unregistered
        self.assertEqual(len(received_statuses), 1)


if __name__ == "__main__":
    unittest.main()
