#!/usr/bin/env python3
"""
Unit tests for Zengge/MagicHome BLE Controller & Protocol Engine.
"""

import sys
import unittest
from pathlib import Path

# Add scripts directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from importlib.machinery import SourceFileLoader
controller = SourceFileLoader("controller", str(Path(__file__).parent.parent / "scripts" / "05_controller.py")).load_module()

UpperTransportLayer = controller.UpperTransportLayer
LowerTransportLayerEncoder = controller.LowerTransportLayerEncoder
LowerTransportLayerDecoder = controller.LowerTransportLayerDecoder
ZenggePayloadBuilder = controller.ZenggePayloadBuilder
ZenggeDeviceStatus = controller.ZenggeDeviceStatus
parse_color_input = controller.parse_color_input
parse_scene_input = controller.parse_scene_input


class TestTransportLayer(unittest.TestCase):

    def test_encode_power_on(self):
        """Test encoding power on frame against live capture: 000180000002030A7123"""
        inner = ZenggePayloadBuilder.power_on()
        self.assertEqual(inner, bytes([0x71, 0x23]))

        upper = UpperTransportLayer(seq=1, cmd_id=0x0A, payload=inner)
        frames = LowerTransportLayerEncoder.generate(upper)
        self.assertEqual(len(frames), 1)
        expected = bytes.fromhex("000180000002030A7123")
        self.assertEqual(frames[0], expected)

    def test_encode_power_off(self):
        """Test encoding power off frame: 000280000002030A7124"""
        inner = ZenggePayloadBuilder.power_off()
        self.assertEqual(inner, bytes([0x71, 0x24]))

        upper = UpperTransportLayer(seq=2, cmd_id=0x0A, payload=inner)
        frames = LowerTransportLayerEncoder.generate(upper)
        expected = bytes.fromhex("000280000002030A7124")
        self.assertEqual(frames[0], expected)

    def test_encode_query_status(self):
        """Test encoding query status against live capture packet 44: 000380000002030A7123"""
        inner = ZenggePayloadBuilder.query_status()
        self.assertEqual(inner, bytes([0x71, 0x23]))

        upper = UpperTransportLayer(seq=3, cmd_id=0x0A, payload=inner)
        frames = LowerTransportLayerEncoder.generate(upper)
        expected = bytes.fromhex("000380000002030A7123")
        self.assertEqual(frames[0], expected)

    def test_encode_hsv_red(self):
        """Test encoding HSV Red against live capture packet 94: 00088000000E0F0AE00100A100646400000000140000"""
        inner = ZenggePayloadBuilder.set_hsv(hue=0, saturation=100, brightness=100)
        upper = UpperTransportLayer(seq=8, cmd_id=0x0A, payload=inner)
        frames = LowerTransportLayerEncoder.generate(upper)
        expected = bytes.fromhex("00088000000E0F0AE00100A100646400000000140000")
        self.assertEqual(frames[0], expected)

    def test_encode_rgb_checksum(self):
        """Test standard RGB checksum calculation."""
        # Pure Red: 0x31, 0xFF, 0x00, 0x00, 0x00, 0x00, 0x0F -> sum = 0x13F -> checksum = 0x3F
        inner = ZenggePayloadBuilder.set_rgb_legacy(255, 0, 0)
        self.assertEqual(inner, bytes.fromhex("31FF000000000F3F"))

        # Pure Green: 0x31, 0x00, 0xFF, 0x00, 0x00, 0x00, 0x0F -> sum = 0x13F -> checksum = 0x3F
        inner_g = ZenggePayloadBuilder.set_rgb_legacy(0, 255, 0)
        self.assertEqual(inner_g, bytes.fromhex("3100FF0000000F3F"))

    def test_encode_scene_checksum(self):
        """Test HagallBjarkan firmware scene command generation (E0 02 00 ...)."""
        scene = ZenggePayloadBuilder.set_scene(0x0A)
        self.assertEqual(scene, bytes.fromhex("E002000AFFFF"))

        scene_flame = ZenggePayloadBuilder.set_scene(0x2C)
        self.assertEqual(scene_flame, bytes.fromhex("E002002CFFFF"))

    def test_decoder_notification(self):
        """Test decoding live GATT notification frame."""
        raw_ntf = bytes.fromhex("04208000004B4C0C7B22636F6465223A302C227061796C6F6164223A2245413831303030303045304132333730303234304630423436343634303030303030303030303030303030303030303030303030227D")
        decoder = LowerTransportLayerDecoder()
        upper = decoder.decode(raw_ntf)
        self.assertIsNotNone(upper)
        self.assertEqual(upper.seq, 0x20)
        self.assertEqual(upper.cmd_id, 0x0C)
        self.assertEqual(upper.type, 1)

        payload_json = upper.payload.decode("utf-8")
        self.assertTrue(payload_json.startswith('{"code":0,"payload":"EA81'))

    def test_status_parsing(self):
        """Test parsing telemetry payloads from captures."""
        # Payload 1: Power ON, Mode 0x70, RGB active, Sat=100%, Bri=100%
        hex1 = "EA8100000E0A23700240F0B46464000000000000000000000000"
        st1 = ZenggeDeviceStatus.from_hex_payload(hex1)
        self.assertIsNotNone(st1)
        self.assertTrue(st1.power)
        self.assertEqual(st1.mode_id, 0x02)
        self.assertEqual(st1.channel_mode, "RGB")
        self.assertEqual(st1.saturation, 100)
        self.assertEqual(st1.brightness, 100)

        # Payload 2: Power OFF, Mode 0x61
        hex2 = "EA8100000E0A246102400F000000646400000000000000000000"
        st2 = ZenggeDeviceStatus.from_hex_payload(hex2)
        self.assertIsNotNone(st2)
        self.assertFalse(st2.power)
        self.assertEqual(st2.mode_id, 0x61)
        self.assertEqual(st2.channel_mode, "WHITE")

        # Payload 3: Red Color, Bri=10%
        hex3 = "EA8100000E0A23610240F078640A000000000000000000000000"
        st3 = ZenggeDeviceStatus.from_hex_payload(hex3)
        self.assertIsNotNone(st3)
        self.assertTrue(st3.power)
        self.assertEqual(st3.brightness, 10)

    def test_color_input_parser(self):
        """Test color parsing for named colors, hex codes, and RGB triples."""
        self.assertEqual(parse_color_input("red"), (255, 0, 0))
        self.assertEqual(parse_color_input("#00ff00"), (0, 255, 0))
        self.assertEqual(parse_color_input("0000ff"), (0, 0, 255))
        self.assertEqual(parse_color_input("255 128 64"), (255, 128, 64))
        self.assertEqual(parse_color_input("255, 128, 64"), (255, 128, 64))

    def test_fragmentation_and_reassembly(self):
        """Test multi-segment payload fragmentation and decoder reassembly."""
        # Create a large payload (> MTU - 8, e.g. 500 bytes)
        large_payload = bytes([i % 256 for i in range(500)])
        upper = UpperTransportLayer(seq=42, cmd_id=0x0A, payload=large_payload)
        
        # Segment with MTU = 100
        frames = LowerTransportLayerEncoder.generate(upper, max_length=100)
        self.assertGreater(len(frames), 1)
        
        # Verify first frame has fragmentation bit (0x40)
        self.assertTrue(bool(frames[0][0] & 0x40))
        
        # Reassemble using decoder
        decoder = LowerTransportLayerDecoder()
        reassembled = None
        for frame in frames:
            res = decoder.decode(frame)
            if res is not None:
                reassembled = res
        
        self.assertIsNotNone(reassembled)
        self.assertEqual(reassembled.seq, 42)
        self.assertEqual(reassembled.cmd_id, 0x0A)
        self.assertEqual(reassembled.payload, large_payload)

    def test_scene_input_parser(self):
        """Test scene parsing by alias and ID."""
        self.assertEqual(parse_scene_input("flame"), 0x2C)
        self.assertEqual(parse_scene_input("colorful"), 0x0A)
        self.assertEqual(parse_scene_input("breathe"), 0x01)
        self.assertEqual(parse_scene_input("0x25"), 0x25)
        self.assertEqual(parse_scene_input("10"), 10)
        self.assertEqual(parse_scene_input("gradient-3"), 0x25)


if __name__ == "__main__":
    unittest.main()
