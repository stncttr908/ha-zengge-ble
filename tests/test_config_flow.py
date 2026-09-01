#!/usr/bin/env python3
"""Unit tests for ZenggeBLEConfigFlow."""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add project root and mock HA
sys.path.insert(0, str(Path(__file__).parent.parent))
import tests.mock_ha  # noqa: F401

from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
from homeassistant.const import CONF_ADDRESS, CONF_NAME

from custom_components.zengge_ble.config_flow import ZenggeBLEConfigFlow, format_mac


class TestConfigFlow(unittest.IsolatedAsyncioTestCase):
    """Test config flow handlers."""

    def test_format_mac(self):
        self.assertEqual(format_mac("aabbccddeeff"), "AA:BB:CC:DD:EE:FF")
        self.assertEqual(format_mac("AA:BB:CC:DD:EE:FF"), "AA:BB:CC:DD:EE:FF")
        self.assertEqual(format_mac("aa-bb-cc-dd-ee-ff"), "AA:BB:CC:DD:EE:FF")
        self.assertEqual(format_mac("a1b2c3d4e5f6"), "A1:B2:C3:D4:E5:F6")

    async def test_bluetooth_discovery_and_confirmation(self):
        flow = ZenggeBLEConfigFlow()
        flow.hass = MagicMock()

        discovery_info = BluetoothServiceInfoBleak(
            name="IOTBT537",
            address="AA:BB:CC:DD:EE:FF",
            service_uuids=["0000ffff-0000-1000-8000-00805f9b34fb"],
            rssi=-55,
        )

        # Discovery step
        result = await flow.async_step_bluetooth(discovery_info)
        self.assertEqual(result["type"], "form")
        self.assertEqual(result["step_id"], "bluetooth_confirm")
        self.assertEqual(flow.unique_id, "AA:BB:CC:DD:EE:FF")

        # Confirm step
        confirm_result = await flow.async_step_bluetooth_confirm(user_input={})
        self.assertEqual(confirm_result["type"], "create_entry")
        self.assertEqual(confirm_result["title"], "IOTBT537")
        self.assertEqual(confirm_result["data"][CONF_ADDRESS], "AA:BB:CC:DD:EE:FF")

    async def test_manual_entry_flow_valid_mac(self):
        flow = ZenggeBLEConfigFlow()
        flow.hass = MagicMock()

        # Initial manual form
        form_result = await flow.async_step_manual()
        self.assertEqual(form_result["type"], "form")
        self.assertEqual(form_result["step_id"], "manual")

        # Submit valid MAC
        create_result = await flow.async_step_manual(
            user_input={CONF_ADDRESS: "11:22:33:44:55:66", CONF_NAME: "Bedside Lamp"}
        )
        self.assertEqual(create_result["type"], "create_entry")
        self.assertEqual(create_result["title"], "Bedside Lamp")
        self.assertEqual(create_result["data"][CONF_ADDRESS], "11:22:33:44:55:66")

    async def test_manual_entry_flow_invalid_mac(self):
        flow = ZenggeBLEConfigFlow()
        flow.hass = MagicMock()

        # Submit invalid MAC
        error_result = await flow.async_step_manual(user_input={CONF_ADDRESS: "invalid-mac-address"})
        self.assertEqual(error_result["type"], "form")
        self.assertIn("address", error_result["errors"])
        self.assertEqual(error_result["errors"]["address"], "invalid_mac")


if __name__ == "__main__":
    unittest.main()
