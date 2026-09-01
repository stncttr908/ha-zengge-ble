#!/usr/bin/env python3
"""Unit tests for ZenggeDataUpdateCoordinator."""

import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

# Add project root and mock HA
sys.path.insert(0, str(Path(__file__).parent.parent))
import tests.mock_ha  # noqa: F401

from bleak.backends.device import BLEDevice

from custom_components.zengge_ble.coordinator import ZenggeDataUpdateCoordinator
from custom_components.zengge_ble.zengge_protocol import ZenggeDeviceStatus, ZenggeLampDevice


class TestCoordinator(unittest.IsolatedAsyncioTestCase):
    """Test coordinator state and push telemetry updates."""

    def setUp(self):
        self.ble_device = BLEDevice("AA:BB:CC:DD:EE:FF", "IOTBT537", {})
        self.device = ZenggeLampDevice(ble_device=self.ble_device)
        self.hass = MagicMock()
        self.coordinator = ZenggeDataUpdateCoordinator(
            hass=self.hass,
            ble_device=self.ble_device,
            device=self.device,
        )

    def test_start_and_stop_listening(self):
        self.coordinator.async_start()
        self.assertIsNotNone(self.coordinator._unregister_callback)

        self.coordinator.async_stop()
        self.assertIsNone(self.coordinator._unregister_callback)

    def test_push_status_update(self):
        self.coordinator.async_start()

        # Simulate push status
        status = ZenggeDeviceStatus.from_hex_payload("EA8100000E0A23610240F0006464000000000000000000000000")
        self.assertIsNotNone(status)

        # Trigger callback through device
        for cb in self.device._callbacks:
            cb(status)

        self.assertEqual(self.coordinator.data, status)
        self.assertTrue(self.coordinator.data.power)
        self.coordinator.async_stop()

    def test_update_ble_device(self):
        new_ble_device = BLEDevice("11:22:33:44:55:66", "Proxy_Lamp", {})
        self.coordinator.update_ble_device(new_ble_device)
        self.assertEqual(self.coordinator.ble_device, new_ble_device)
        self.assertEqual(self.coordinator.device.address, "11:22:33:44:55:66")

    async def test_async_update_data_connected(self):
        status = ZenggeDeviceStatus.from_hex_payload("EA8100000E0A23610240F0006464000000000000000000000000")
        self.device.query_status = AsyncMock(return_value=status)
        self.device.connect = AsyncMock(return_value=True)

        result = await self.coordinator._async_update_data()
        self.assertEqual(result, status)


if __name__ == "__main__":
    unittest.main()
