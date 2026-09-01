#!/usr/bin/env python3
"""Unit tests for ZenggeHBLightEntity."""

import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

# Add project root and mock HA
sys.path.insert(0, str(Path(__file__).parent.parent))
import tests.mock_ha  # noqa: F401

from bleak.backends.device import BLEDevice
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_EFFECT,
    ATTR_HS_COLOR,
    ATTR_RGB_COLOR,
    ColorMode,
)
from homeassistant.config_entries import ConfigEntry

from custom_components.zengge_ble.coordinator import ZenggeDataUpdateCoordinator
from custom_components.zengge_ble.light import ZenggeHBLightEntity
from custom_components.zengge_ble.zengge_protocol import ZenggeDeviceStatus, ZenggeLampDevice


class TestZenggeLightEntity(unittest.IsolatedAsyncioTestCase):
    """Test Home Assistant Light Entity state mapping and command dispatching."""

    def setUp(self):
        self.ble_device = BLEDevice("AA:BB:CC:DD:EE:FF", "IOTBT537", {})
        self.device = ZenggeLampDevice(ble_device=self.ble_device)
        self.device.power_on = AsyncMock()
        self.device.power_off = AsyncMock()
        self.device.set_rgb = AsyncMock()
        self.device.set_hsv = AsyncMock()
        self.device.set_cct = AsyncMock()
        self.device.set_brightness = AsyncMock()
        self.device.set_scene = AsyncMock()
        self.device.set_scene_magichome = AsyncMock()

        self.hass = MagicMock()
        self.coordinator = ZenggeDataUpdateCoordinator(
            hass=self.hass,
            ble_device=self.ble_device,
            device=self.device,
        )
        self.entry = ConfigEntry(unique_id="AA:BB:CC:DD:EE:FF", title="Living Room Lamp")
        self.entity = ZenggeHBLightEntity(self.coordinator, self.entry)

    def test_initial_state_none(self):
        self.assertIsNone(self.entity.is_on)
        self.assertIsNone(self.entity.brightness)
        self.assertIsNone(self.entity.hs_color)
        self.assertIsNone(self.entity.color_temp_kelVIN if hasattr(self.entity, "color_temp_kelVIN") else self.entity.color_temp_kelvin)
        self.assertIsNone(self.entity.effect)
        self.assertEqual(self.entity.unique_id, "AA:BB:CC:DD:EE:FF_light")

    def test_rgb_state_reflection(self):
        # Power ON, Color/CCT mode 0x61, RGB mode (0xF0), Hue=180 (div2=90 / 0x5A), Sat=80% (0x50), Bri=60% (0x3C)
        hex_payload = "EA8100000E0A23610240F05A503C000000000000000000000000"
        status = ZenggeDeviceStatus.from_hex_payload(hex_payload)
        self.coordinator.data = status

        self.assertTrue(self.entity.is_on)
        self.assertEqual(self.entity.color_mode, ColorMode.HS)
        self.assertEqual(self.entity.hs_color, (180.0, 80.0))
        self.assertEqual(self.entity.brightness, int(round(0.6 * 255)))
        self.assertIsNone(self.entity.color_temp_kelvin)
        self.assertIsNone(self.entity.effect)

    def test_white_cct_state_reflection(self):
        # Power ON, Mode 0x61, White mode (0x0F), Warm=0, Cool=100% (0x64), Bri=100% (0x64)
        hex_payload = "EA8100000E0A236102400F006464006400000000000000000000"
        status = ZenggeDeviceStatus.from_hex_payload(hex_payload)
        self.coordinator.data = status

        self.assertTrue(self.entity.is_on)
        self.assertEqual(self.entity.color_mode, ColorMode.COLOR_TEMP)
        self.assertEqual(self.entity.color_temp_kelvin, 6500)  # 100% cool = 6500K
        self.assertIsNone(self.entity.hs_color)

    def test_scene_state_reflection(self):
        # Power ON, Flame scene 0x2C
        hex_payload = "EA8100000E0A232C0240F0006464000000000000000000000000"
        status = ZenggeDeviceStatus.from_hex_payload(hex_payload)
        self.coordinator.data = status

        self.assertTrue(self.entity.is_on)
        self.assertEqual(self.entity.effect, "Custom Flame")

    async def test_async_turn_on_power_only(self):
        await self.entity.async_turn_on()
        self.device.power_on.assert_awaited_once()

    async def test_async_turn_off(self):
        await self.entity.async_turn_off()
        self.device.power_off.assert_awaited_once()

    async def test_async_turn_on_effect(self):
        await self.entity.async_turn_on(**{ATTR_EFFECT: "Flame"})
        self.device.set_scene.assert_awaited_once_with(0x2C)

        await self.entity.async_turn_on(**{ATTR_EFFECT: "Breathe"})
        self.device.set_scene.assert_awaited_with(0x01)

    async def test_async_turn_on_hs_color(self):
        await self.entity.async_turn_on(**{ATTR_HS_COLOR: (120.0, 100.0), ATTR_BRIGHTNESS: 255})
        self.device.set_hsv.assert_awaited_once_with(120, 100, 100)

    async def test_async_turn_on_rgb_color(self):
        await self.entity.async_turn_on(**{ATTR_RGB_COLOR: (255, 0, 0)})
        self.device.set_rgb.assert_awaited_once_with(255, 0, 0)

    async def test_async_turn_on_color_temp(self):
        # 2700K -> 0% CCT
        await self.entity.async_turn_on(**{ATTR_COLOR_TEMP_KELVIN: 2700, ATTR_BRIGHTNESS: 128})
        self.device.set_cct.assert_awaited_once_with(0, 50)

        # 6500K -> 100% CCT
        await self.entity.async_turn_on(**{ATTR_COLOR_TEMP_KELVIN: 6500, ATTR_BRIGHTNESS: 255})
        self.device.set_cct.assert_awaited_with(100, 100)

    async def test_async_turn_on_brightness(self):
        await self.entity.async_turn_on(**{ATTR_BRIGHTNESS: 128})
        self.device.set_brightness.assert_awaited_once_with(50)


if __name__ == "__main__":
    unittest.main()
