#!/usr/bin/env python3
"""Unit tests for zengge_protocol module."""

import sys
import unittest
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from custom_components.zengge_ble.const import (
    CARRIER_WAVE_EFFECT_LIST,
    EFFECT_LIST,
    EFFECT_NAME_TO_ID,
    EFFECT_SLUG_TO_ID,
    PRODUCT_ID_CARRIER_WAVE_STRING,
    SCENE_PRESETS,
)
from custom_components.zengge_ble.zengge_protocol import (
    LowerTransportLayerDecoder,
    LowerTransportLayerEncoder,
    UpperTransportLayer,
    ZenggeDeviceStatus,
    ZenggePayloadBuilder,
    parse_service_data_product_info,
)


class TestProtocolSerialization(unittest.TestCase):
    """Test lower and upper transport layer serialization."""

    def test_encode_power_on(self):
        inner = ZenggePayloadBuilder.power_on()
        self.assertEqual(inner, bytes([0x71, 0x23]))
        upper = UpperTransportLayer(seq=1, cmd_id=0x0A, payload=inner)
        frames = LowerTransportLayerEncoder.generate(upper)
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0], bytes.fromhex("000180000002030A7123"))

    def test_encode_power_off(self):
        inner = ZenggePayloadBuilder.power_off()
        self.assertEqual(inner, bytes([0x71, 0x24]))
        upper = UpperTransportLayer(seq=2, cmd_id=0x0A, payload=inner)
        frames = LowerTransportLayerEncoder.generate(upper)
        self.assertEqual(frames[0], bytes.fromhex("000280000002030A7124"))

    def test_encode_query_status(self):
        inner = ZenggePayloadBuilder.query_status()
        self.assertEqual(inner, bytes([0x71, 0x23]))
        upper = UpperTransportLayer(seq=3, cmd_id=0x0A, payload=inner)
        frames = LowerTransportLayerEncoder.generate(upper)
        self.assertEqual(frames[0], bytes.fromhex("000380000002030A7123"))

    def test_encode_hsv_red(self):
        inner = ZenggePayloadBuilder.set_hsv(hue=0, saturation=100, brightness=100)
        upper = UpperTransportLayer(seq=8, cmd_id=0x0A, payload=inner)
        frames = LowerTransportLayerEncoder.generate(upper)
        self.assertEqual(frames[0], bytes.fromhex("00088000000E0F0AE00100A100646400000000140000"))

    def test_encode_cct(self):
        inner = ZenggePayloadBuilder.set_cct(cct_percent=50, brightness=80)
        self.assertEqual(inner, bytes.fromhex("E00100B100000032500000140000"))

    def test_encode_rgb_legacy(self):
        inner = ZenggePayloadBuilder.set_rgb_legacy(255, 0, 0)
        self.assertEqual(inner, bytes.fromhex("31FF000000000F3F"))

    def test_encode_scene(self):
        inner = ZenggePayloadBuilder.set_scene(0x2C)  # Flame
        self.assertEqual(inner, bytes.fromhex("E002002CFFFF"))

    def test_decode_json_notification(self):
        raw_ntf = bytes.fromhex(
            "04208000004B4C0C7B22636F6465223A302C227061796C6F6164223A2245413831303030303045304132333730303234304630423436343634303030303030303030303030303030303030303030303030227D"
        )
        decoder = LowerTransportLayerDecoder()
        upper = decoder.decode(raw_ntf)
        self.assertIsNotNone(upper)
        self.assertEqual(upper.seq, 0x20)
        self.assertEqual(upper.cmd_id, 0x0C)
        self.assertEqual(upper.type, 1)

    def test_segmentation_reassembly(self):
        large_payload = bytes([i % 256 for i in range(600)])
        upper = UpperTransportLayer(seq=99, cmd_id=0x0A, payload=large_payload)
        frames = LowerTransportLayerEncoder.generate(upper, max_length=128)
        self.assertGreater(len(frames), 1)

        decoder = LowerTransportLayerDecoder()
        reassembled = None
        for frame in frames:
            res = decoder.decode(frame)
            if res is not None:
                reassembled = res

        self.assertIsNotNone(reassembled)
        self.assertEqual(reassembled.seq, 99)
        self.assertEqual(reassembled.cmd_id, 0x0A)
        self.assertEqual(reassembled.payload, large_payload)


class TestStatusParsing(unittest.TestCase):
    """Test parsing 26-byte status telemetry."""

    def test_parse_color_mode_status(self):
        # Power ON, Color/CCT mode 0x61, RGB active, Hue=0 (div2=0), Sat=100%, Bri=100%
        hex_str = "EA8100000E0A23610240F0006464000000000000000000000000"
        status = ZenggeDeviceStatus.from_hex_payload(hex_str)
        self.assertIsNotNone(status)
        self.assertTrue(status.power)
        self.assertEqual(status.mode_id, 0x61)
        self.assertEqual(status.channel_mode, "RGB")
        self.assertEqual(status.hue, 0)
        self.assertEqual(status.saturation, 100)
        self.assertEqual(status.brightness, 100)
        self.assertFalse(status.is_scene_mode)

    def test_parse_white_mode_status(self):
        # Power OFF, Mode 0x61, White active (0x0F), Warm=100, Cool=100
        hex_str = "EA8100000E0A246102400F000000646400000000000000000000"
        status = ZenggeDeviceStatus.from_hex_payload(hex_str)
        self.assertIsNotNone(status)
        self.assertFalse(status.power)
        self.assertEqual(status.channel_mode, "WHITE")
        self.assertEqual(status.warm_white, 100)
        self.assertEqual(status.cool_white, 100)

    def test_parse_scene_mode_status(self):
        # Power ON, Flame scene 0x2C
        hex_str = "EA8100000E0A232C0240F0006464000000000000000000000000"
        status = ZenggeDeviceStatus.from_hex_payload(hex_str)
        self.assertIsNotNone(status)
        self.assertTrue(status.power)
        self.assertEqual(status.mode_id, 0x2C)
        self.assertTrue(status.is_scene_mode)
        self.assertEqual(status.mode_name, "Scene: Custom Flame")

    def test_all_scenes_mapped(self):
        self.assertGreaterEqual(len(EFFECT_LIST), 26)
        self.assertIn("Flame", EFFECT_NAME_TO_ID)
        self.assertIn("flame", EFFECT_SLUG_TO_ID)
        self.assertIn("Breathe", EFFECT_NAME_TO_ID)
        self.assertIn("Colorful", EFFECT_NAME_TO_ID)


class TestCarrierWaveProtocol(unittest.TestCase):
    """Test Carrier-Wave Symphony (productId 0x00C5 / IOTBTD84) protocol."""

    def test_parse_service_data_product_info(self):
        pid, fw, led = parse_service_data_product_info(
            {"00005a00-0000-1000-8000-00805f9b34fb": bytes.fromhex("5b070865f041dd8400c543080128")}
        )
        self.assertEqual(pid, PRODUCT_ID_CARRIER_WAVE_STRING)
        self.assertEqual(fw, 0x43)
        self.assertEqual(led, 8)

        pid2, fw2, led2 = parse_service_data_product_info(
            {"00005a02-0000-1000-8000-00805f9b34fb": bytes.fromhex("5b07e498bb69e537000e330a0100")}
        )
        self.assertEqual(pid2, 0x000E)
        self.assertEqual(fw2, 0x33)
        self.assertEqual(led2, 10)

    def test_carrier_wave_builders_match_captures(self):
        self.assertEqual(ZenggePayloadBuilder.query_status_v2(), bytes.fromhex("EA818A8B59"))
        self.assertEqual(ZenggePayloadBuilder.power_on_v2(), bytes.fromhex("E001002300000000000000000000"))
        self.assertEqual(ZenggePayloadBuilder.power_off_v2(), bytes.fromhex("E001002400000000000000000000"))

        # Purple 271 deg, 100% sat, 100% bri -> 0x87 0xE4 0x64
        self.assertEqual(
            ZenggePayloadBuilder.set_hsv_carrier_wave(271, 100, 100),
            bytes.fromhex("E00100C187E46400000000140000"),
        )
        # Warm White 21 deg, 95% sat, 100% bri -> 0x0A 0xDF 0x64
        self.assertEqual(
            ZenggePayloadBuilder.set_hsv_carrier_wave(21, 95, 100),
            bytes.fromhex("E00100C10ADF6400000000140000"),
        )
        # Christmas1 @ 30% brightness
        self.assertEqual(
            ZenggePayloadBuilder.build_carrier_wave_effect("Christmas1", brightness=30),
            bytes.fromhex("E121001E02000150500000000000000300646400003C646400000000640000"),
        )
        # Multi-color string preset @ 100% brightness
        self.assertEqual(
            ZenggePayloadBuilder.build_carrier_wave_effect("Red & Green", brightness=100),
            bytes.fromhex("EC0700640200646400003C64640000"),
        )
        self.assertEqual(len(CARRIER_WAVE_EFFECT_LIST), 79)

    def test_parse_carrier_wave_telemetry(self):
        # Solid Purple 271 deg, 100% sat, 100% bri, 25 points
        status = ZenggeDeviceStatus.from_hex_payload("EA810000C508232414500087E4640000000019000000013B010019")
        self.assertIsNotNone(status)
        self.assertEqual(status.product_id, 197)
        self.assertEqual(status.led_version, 8)
        self.assertTrue(status.power)
        self.assertEqual(status.channel_mode, "RGB")
        self.assertEqual(status.hue, 271)
        self.assertEqual(status.saturation, 100)
        self.assertEqual(status.brightness, 100)
        self.assertEqual(status.point_count, 25)
        self.assertFalse(status.is_scene_mode)

        # Built-in Effect Christmas1 (mode 0x25, sub_mode 0x02, speed 0x50)
        eff_status = ZenggeDeviceStatus.from_hex_payload("EA810000C50823250250006BCE5D005D000019000000013B010019")
        self.assertIsNotNone(eff_status)
        self.assertTrue(eff_status.is_scene_mode)
        self.assertEqual(eff_status.mode_id, 0x25)
        self.assertEqual(eff_status.sub_mode_id, 0x02)
        self.assertEqual(eff_status.speed, 0x50)

        # String Preset mode 0x24 sub_mode 0x01
        preset_status = ZenggeDeviceStatus.from_hex_payload("EA810000C50823240150003C64640000000019000000013B010019")
        self.assertIsNotNone(preset_status)
        self.assertTrue(preset_status.is_scene_mode)


if __name__ == "__main__":
    unittest.main()
