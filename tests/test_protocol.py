#!/usr/bin/env python3
"""Unit tests for zengge_protocol module."""

import sys
import unittest
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from custom_components.zengge_ble.const import (
    EFFECT_LIST,
    EFFECT_NAME_TO_ID,
    EFFECT_SLUG_TO_ID,
    SCENE_PRESETS,
)
from custom_components.zengge_ble.zengge_protocol import (
    LowerTransportLayerDecoder,
    LowerTransportLayerEncoder,
    UpperTransportLayer,
    ZenggeDeviceStatus,
    ZenggePayloadBuilder,
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
        self.assertEqual(status.mode_name, "Scene: Flame")

    def test_all_scenes_mapped(self):
        self.assertEqual(len(SCENE_PRESETS), 26)
        self.assertEqual(len(EFFECT_LIST), 26)
        self.assertIn("Flame", EFFECT_NAME_TO_ID)
        self.assertIn("flame", EFFECT_SLUG_TO_ID)
        self.assertIn("Breathe", EFFECT_NAME_TO_ID)
        self.assertIn("Colorful", EFFECT_NAME_TO_ID)


if __name__ == "__main__":
    unittest.main()
