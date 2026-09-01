#!/usr/bin/env python3
"""
05_controller.py
Standalone Python BLE Controller for Zengge/MagicHome Smart Lamp (HagallBjarkan Transport).

Implements:
- Pure-Python LowerTransportLayerEncoder & Decoder
- UpperTransportLayer encapsulation
- Asynchronous BleakClient connection & notification listener on 0xFF02
- CLI and interactive REPL for power, RGB, brightness, CCT, scenes, and status
"""

from __future__ import annotations

import argparse
import asyncio
import colorsys
import json
import logging
import math
import re
import sys
from dataclasses import dataclass
from typing import Callable, Optional

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

console = Console()
logger = logging.getLogger("zengge_ble")

# ==============================================================================
# Protocol Constants & UUIDs
# ==============================================================================
SERVICE_UUID = "0000ffff-0000-1000-8000-00805f9b34fb"
WRITE_UUID = "0000ff01-0000-1000-8000-00805f9b34fb"
NOTIFY_UUID = "0000ff02-0000-1000-8000-00805f9b34fb"

OTA_SERVICE_UUID = "0000fe00-0000-1000-8000-00805f9b34fb"
OTA_WRITE_UUID = "0000ff11-0000-1000-8000-00805f9b34fb"
OTA_NOTIFY_UUID = "0000ff22-0000-1000-8000-00805f9b34fb"

CMD_ID_APP = 0x0A
CMD_ID_NOTIF = 0x0C

MARKER_MIN_VALUE = 0x8000  # 16-bit Short.MIN_VALUE marker (-32768 in Java)

# Built-in Preset Scene Modes (HagallBjarkan Firmware Opcodes: E0 02 00 <ID> FF FF)
SCENE_PRESETS = {
    # Custom Dynamic Animation Presets (0x25 - 0x2C)
    0x25: ("Three Color Gradient", "gradient-3"),
    0x26: ("Five Color Jump", "jump-5"),
    0x27: ("Colorful Breath", "colorful-breath"),
    0x28: ("Heartbeat", "heartbeat"),
    0x29: ("Lightning", "lightning"),
    0x2C: ("Flame", "flame"),
    # Built-in Lighting Presets (0x01 - 0x14)
    0x01: ("Breathe", "breathe"),
    0x02: ("Step Change", "step-change"),
    0x03: ("Rhythm Change", "rhythm-change"),
    0x04: ("Leisure", "leisure"),
    0x05: ("Night Light", "night-light"),
    0x06: ("Good Night", "good-night"),
    0x07: ("Read", "read"),
    0x08: ("Work", "work"),
    0x09: ("Grassland", "grassland"),
    0x0A: ("Colorful", "colorful"),
    0x0B: ("Dazzling", "dazzling"),
    0x0C: ("Gorgeous", "gorgeous"),
    0x0D: ("Blue Sky", "blue-sky"),
    0x0E: ("Sunflower", "sunflower"),
    0x0F: ("Forest", "forest"),
    0x10: ("Mediterranean", "mediterranean"),
    0x11: ("French Style", "french-style"),
    0x12: ("American Style", "american-style"),
    0x13: ("Birthday Party", "birthday"),
    0x14: ("Wedding Day", "wedding"),
}

COLOR_NAMES = {
    "red": (255, 0, 0),
    "green": (0, 255, 0),
    "blue": (0, 0, 255),
    "white": (255, 255, 255),
    "warmwhite": (255, 200, 100),
    "coolwhite": (200, 220, 255),
    "yellow": (255, 255, 0),
    "cyan": (0, 255, 255),
    "magenta": (255, 0, 255),
    "purple": (128, 0, 128),
    "orange": (255, 128, 0),
    "pink": (255, 105, 180),
    "teal": (0, 128, 128),
    "lime": (50, 205, 50),
}


# ==============================================================================
# Protocol Data Structures & Transport Encoder/Decoder
# ==============================================================================

@dataclass
class UpperTransportLayer:
    """Represents the upper application-level transport packet."""
    ack: bool = False
    protect: bool = False
    type: int = 0
    seq: int = 1
    cmd_id: int = CMD_ID_APP
    payload: bytes = b""


class LowerTransportLayerEncoder:
    """
    Pure Python port of com.zengge.hagallbjarkan.protocol.zgble.LowerTransportLayerEncoder
    """

    @staticmethod
    def _create_ctrl(protect: bool, ack: bool, is_fragmented: bool, version: int = 0) -> int:
        ctrl = 0
        if is_fragmented:
            ctrl |= (1 << 6)
        if protect:
            ctrl |= (1 << 5)
        if ack:
            ctrl |= (1 << 4)
        ctrl |= (version & 0x03)
        return ctrl & 0xFF

    @classmethod
    def generate(cls, upper: UpperTransportLayer, max_length: int = 255) -> list[bytes]:
        """
        Encapsulates upper payload into one or more Lower Transport Layer frame chunks.
        """
        payload = upper.payload
        max_inner = max_length - 8

        if len(payload) <= max_inner:
            # Single unsegmented packet
            frame = bytearray(len(payload) + 8)
            frame[0] = cls._create_ctrl(upper.protect, upper.ack, False, 0)
            frame[1] = upper.seq & 0xFF
            frame[2] = (MARKER_MIN_VALUE >> 8) & 0xFF  # 0x80
            frame[3] = MARKER_MIN_VALUE & 0xFF         # 0x00
            frame[4] = (len(payload) >> 8) & 0xFF
            frame[5] = len(payload) & 0xFF
            frame[6] = (len(payload) + 1) & 0xFF
            frame[7] = upper.cmd_id & 0xFF
            frame[8:] = payload
            return [bytes(frame)]

        # Multi-segment fragmentation
        rem_len = (len(payload) - max_length) + 8
        step = max_length - 5
        seg_count = 2 if rem_len <= step else ((rem_len // step) + 1 if rem_len % step == 0 else (rem_len // step) + 2)

        segments = []
        offset = 0
        for i in range(seg_count):
            if i == 0:
                frame = bytearray(max_length)
                frame[0] = cls._create_ctrl(upper.protect, upper.ack, True, 0)
                frame[1] = upper.seq & 0xFF
                frame[2] = 0x00
                frame[3] = 0x00
                frame[4] = (len(payload) >> 8) & 0xFF
                frame[5] = len(payload) & 0xFF
                frame[6] = (max_length - 7) & 0xFF
                frame[7] = upper.cmd_id & 0xFF
                frame[8:max_length] = payload[0:max_inner]
                offset = max_inner
                segments.append(bytes(frame))
            else:
                chunk_len = min(len(payload) - offset, max_length - 5)
                seg_marker = (0x8000 | i) if (i == seg_count - 1) else i
                frame = bytearray(chunk_len + 5)
                frame[0] = cls._create_ctrl(upper.protect, upper.ack, True, 0)
                frame[1] = upper.seq & 0xFF
                frame[2] = (seg_marker >> 8) & 0xFF
                frame[3] = seg_marker & 0xFF
                frame[4] = chunk_len & 0xFF
                frame[5:] = payload[offset:offset + chunk_len]
                offset += chunk_len
                segments.append(bytes(frame))

        return segments


class LowerTransportLayerDecoder:
    """
    Pure Python port of com.zengge.hagallbjarkan.protocol.zgble.LowerTransportLayerDecoder
    Reassembles single/segmented frames into UpperTransportLayer.
    """

    def __init__(self):
        self.reset()

    def reset(self):
        self.receive_seq = -1
        self.total_length = -1
        self.prev_segment_num = -1
        self.cmd_id = -1
        self.prev_index = -1
        self.buffer = bytearray()

    def decode(self, raw: bytes) -> Optional[UpperTransportLayer]:
        if not raw:
            return None

        ctrl = raw[0]
        is_fragmented = bool(ctrl & 0x40)
        is_protect = bool(ctrl & 0x20)
        is_ack = bool(ctrl & 0x10)
        pkt_type = (ctrl & 0x0C) >> 2

        if not is_fragmented:
            if len(raw) < 7:
                return None
            marker = (raw[2] << 8) | raw[3]
            if marker != 0x8000:
                return None
            total_len = (raw[4] << 8) | raw[5]
            seq = raw[1]
            cmd_id = raw[7] if len(raw) > 7 else 0
            payload = raw[8:8 + total_len]
            self.reset()
            return UpperTransportLayer(
                ack=is_ack,
                protect=is_protect,
                type=pkt_type,
                seq=seq,
                cmd_id=cmd_id,
                payload=payload,
            )

        # Fragmented handling
        if len(raw) < 4:
            self.reset()
            return None

        seg_ctrl = ((raw[2] & 0x7F) << 8) | raw[3]
        is_last = bool(raw[2] & 0x80)

        if ((raw[2] << 8) | raw[3]) == 0:
            # First segment
            self.reset()
            if len(raw) < 8:
                return None
            self.receive_seq = raw[1]
            self.total_length = (raw[4] << 8) | raw[5]
            self.buffer = bytearray(self.total_length)
            self.prev_segment_num = seg_ctrl
            self.cmd_id = raw[7]
            chunk = raw[8:]
            self.buffer[0:len(chunk)] = chunk
            self.prev_index = len(chunk)
            return None
        elif self.receive_seq == raw[1] and self.prev_segment_num == seg_ctrl - 1:
            # Intermediate / final segment
            chunk_len = raw[4]
            chunk = raw[5:5 + chunk_len]
            self.buffer[self.prev_index:self.prev_index + len(chunk)] = chunk
            self.prev_segment_num = seg_ctrl
            self.prev_index += len(chunk)

            if is_last:
                seq = self.receive_seq
                cmd_id = self.cmd_id
                payload = bytes(self.buffer)
                self.reset()
                return UpperTransportLayer(
                    ack=is_ack,
                    protect=is_protect,
                    type=pkt_type,
                    seq=seq,
                    cmd_id=cmd_id,
                    payload=payload,
                )
            return None
        else:
            self.reset()
            return None


# ==============================================================================
# Device Status & Command Builders
# ==============================================================================

@dataclass
class ZenggeDeviceStatus:
    """Parsed lamp telemetry state."""
    raw_hex: str
    power: bool
    mode_id: int
    mode_name: str
    channel_mode: str  # "RGB" or "WHITE"
    hue: int           # 0..360 deg
    saturation: int    # 0..100%
    brightness: int    # 0..100%
    warm_white: int    # 0..100%
    cool_white: int    # 0..100%
    rgb_approx: tuple[int, int, int]

    @classmethod
    def from_hex_payload(cls, hex_str: str) -> Optional[ZenggeDeviceStatus]:
        """
        Parses 26-byte status payload (e.g. 'EA8100000E0A23610240F0006464000000000000000000000000')
        """
        try:
            b = bytes.fromhex(hex_str.strip().replace(" ", ""))
            if len(b) < 14:
                return None

            power = (b[6] == 0x23)
            mode_id = b[7]
            mode_name = "Unknown"
            if mode_id == 0x61:
                mode_name = "Color / CCT"
            elif mode_id == 0x70:
                mode_name = "White / Static"
            elif mode_id in SCENE_PRESETS:
                mode_name = f"Scene: {SCENE_PRESETS[mode_id][0]}"

            channel_flag = b[10]
            is_rgb = (channel_flag == 0xF0)
            channel_mode = "RGB" if is_rgb else "WHITE"

            hue_div2 = b[11]
            hue = min(360, hue_div2 * 2)
            saturation = b[12]
            brightness = b[13]
            warm_white = b[14] if len(b) > 14 else 0
            cool_white = b[15] if len(b) > 15 else 0

            # Compute approximate RGB
            if is_rgb:
                r_f, g_f, b_f = colorsys.hsv_to_rgb(hue / 360.0, saturation / 100.0, brightness / 100.0)
                rgb_approx = (int(r_f * 255), int(g_f * 255), int(b_f * 255))
            else:
                rgb_approx = (255, 240, 220)

            return cls(
                raw_hex=hex_str,
                power=power,
                mode_id=mode_id,
                mode_name=mode_name,
                channel_mode=channel_mode,
                hue=hue,
                saturation=saturation,
                brightness=brightness,
                warm_white=warm_white,
                cool_white=cool_white,
                rgb_approx=rgb_approx,
            )
        except Exception as e:
            logger.debug(f"Failed to parse status hex {hex_str}: {e}")
            return None


class ZenggePayloadBuilder:
    """Builds inner payloads for Zengge commands."""

    @staticmethod
    def _checksum(payload: bytes) -> int:
        return sum(payload) & 0xFF

    @classmethod
    def power_on(cls) -> bytes:
        # 0x71 0x23 is the primary HagallBjarkan power-on / status trigger
        return bytes([0x71, 0x23])

    @classmethod
    def power_off(cls) -> bytes:
        # 0x71 0x24 is the primary HagallBjarkan power-off command
        return bytes([0x71, 0x24])

    @classmethod
    def query_status(cls) -> bytes:
        return bytes([0x71, 0x23])

    @classmethod
    def set_rgb(cls, r: int, g: int, b: int) -> bytes:
        """
        Converts RGB to HagallBjarkan HSV format (0xA1) matching live captures.
        """
        r_f = max(0, min(255, int(r))) / 255.0
        g_f = max(0, min(255, int(g))) / 255.0
        b_f = max(0, min(255, int(b))) / 255.0
        h, s, v = colorsys.rgb_to_hsv(r_f, g_f, b_f)
        hue_deg = int(round(h * 360)) % 360
        sat_pct = int(round(s * 100))
        bri_pct = int(round(v * 100))
        if bri_pct == 0:
            bri_pct = 1  # Avoid accidental 0 brightness on black unless explicitly off
        return cls.set_hsv(hue_deg, sat_pct, bri_pct)

    @classmethod
    def set_rgb_legacy(cls, r: int, g: int, b: int) -> bytes:
        """Legacy 0x31 RGB frame."""
        r = max(0, min(255, int(r)))
        g = max(0, min(255, int(g)))
        b = max(0, min(255, int(b)))
        cmd = bytearray([0x31, r, g, b, 0x00, 0x00, 0x0F])
        cmd.append(cls._checksum(cmd))
        return bytes(cmd)

    @classmethod
    def set_hsv(cls, hue: int, saturation: int, brightness: int) -> bytes:
        """Extended HagallBjarkan 0xA1 HSV command."""
        h_div2 = max(0, min(180, int(hue // 2)))
        sat = max(0, min(100, int(saturation)))
        bri = max(0, min(100, int(brightness)))
        return bytes([0xE0, 0x01, 0x00, 0xA1, h_div2, sat, bri, 0x00, 0x00, 0x00, 0x00, 0x14, 0x00, 0x00])

    @classmethod
    def set_cct(cls, cct_percent: int, brightness: int) -> bytes:
        """Extended HagallBjarkan 0xB1 CCT command."""
        cct = max(0, min(100, int(cct_percent)))
        bri = max(0, min(100, int(brightness)))
        return bytes([0xE0, 0x01, 0x00, 0xB1, 0x00, 0x00, 0x00, cct, bri, 0x00, 0x00, 0x14, 0x00, 0x00])

    @classmethod
    def set_white(cls, warm: int, cold: int) -> bytes:
        warm = max(0, min(255, int(warm)))
        cold = max(0, min(255, int(cold)))
        cmd = bytearray([0x31, 0x00, 0x00, 0x00, warm, cold, 0x0F])
        cmd.append(cls._checksum(cmd))
        return bytes(cmd)

    @classmethod
    def set_scene(cls, scene_id: int, speed: int = 16) -> bytes:
        """
        Constructs a HagallBjarkan native firmware scene activation frame (0xE0 0x02 0x00 ...).
        Inner Frame: E0 02 00 <scene_id> FF FF
        """
        return bytes([0xE0, 0x02, 0x00, scene_id & 0xFF, 0xFF, 0xFF])


# ==============================================================================
# Async BLE Client Engine
# ==============================================================================

class ZenggeLampClient:
    """
    High-level asynchronous client managing BLE connection and protocol exchange.
    """

    def __init__(self, target_address: str, target_device: Optional[BLEDevice] = None):
        self.address = target_address
        self._target_device = target_device
        self.client: Optional[BleakClient] = None
        self._seq = 1
        self._decoder = LowerTransportLayerDecoder()
        self._status_future: Optional[asyncio.Future[ZenggeDeviceStatus]] = None
        self._latest_status: Optional[ZenggeDeviceStatus] = None
        self._callbacks: list[Callable[[ZenggeDeviceStatus], None]] = []

    @property
    def next_seq(self) -> int:
        s = self._seq
        self._seq = (self._seq + 1) & 0xFF
        if self._seq == 0:
            self._seq = 1
        return s

    @property
    def is_connected(self) -> bool:
        return self.client is not None and self.client.is_connected

    def add_status_callback(self, cb: Callable[[ZenggeDeviceStatus], None]):
        self._callbacks.append(cb)

    async def connect(self, timeout: float = 15.0) -> bool:
        """Connects to the lamp and enables telemetry notifications."""
        console.print(f"[cyan]Resolving and connecting to {self.address}...[/cyan]")
        try:
            if self._target_device is not None:
                target = self._target_device
            else:
                device = await BleakScanner.find_device_by_address(self.address, timeout=min(timeout, 5.0))
                if not device and "IOTBT" in self.address.upper():
                    device = await BleakScanner.find_device_by_name("IOTBT537", timeout=min(timeout, 5.0))
                target = device if device is not None else self.address

            self.client = BleakClient(target, timeout=timeout)
            await self.client.connect()
            if not self.client.is_connected:
                console.print(f"[bold red]Connection to {self.address} failed.[/bold red]")
                return False

            console.print(f"[green]✓ Connected to {self.address}[/green]")
            # Subscribe to notifications if 0xFF02 exists
            try:
                await self.client.start_notify(NOTIFY_UUID, self._on_notification)
                console.print("[dim]✓ Telemetry notifications enabled (0xFF02)[/dim]")
            except Exception as ne:
                console.print(f"[dim]Note: 0xFF02 notification characteristic: {ne}[/dim]")
            return True
        except Exception as e:
            console.print(f"[bold red]BLE Connection error:[/bold red] {e}")
            return False

    async def disconnect(self):
        """Disconnects cleanly."""
        if self.client and self.client.is_connected:
            try:
                await self.client.stop_notify(NOTIFY_UUID)
            except Exception:
                pass
            await self.client.disconnect()
            console.print(f"[yellow]Disconnected from {self.address}[/yellow]")
        self.client = None

    def _on_notification(self, sender: int, data: bytearray):
        """Handles incoming GATT notifications on 0xFF02."""
        raw = bytes(data)
        upper = self._decoder.decode(raw)
        if upper and upper.payload:
            try:
                payload_str = upper.payload.decode("utf-8")
                res = json.loads(payload_str)
                hex_payload = res.get("payload", "")
                status = ZenggeDeviceStatus.from_hex_payload(hex_payload)
                if status:
                    self._latest_status = status
                    if self._status_future and not self._status_future.done():
                        self._status_future.set_result(status)
                    for cb in self._callbacks:
                        try:
                            cb(status)
                        except Exception:
                            pass
            except Exception as e:
                logger.debug(f"Error parsing notification JSON: {e}")

    async def send_command(self, payload: bytes, wait_response: bool = False, timeout: float = 2.5) -> Optional[ZenggeDeviceStatus]:
        """
        Wraps inner payload in LowerTransportLayer frame and transmits over 0xFF01.
        """
        if not self.is_connected or self.client is None:
            raise ConnectionError("Device not connected")

        upper = UpperTransportLayer(
            ack=False,
            protect=False,
            type=0,
            seq=self.next_seq,
            cmd_id=CMD_ID_APP,
            payload=payload,
        )
        frames = LowerTransportLayerEncoder.generate(upper)

        if wait_response:
            loop = asyncio.get_running_loop()
            self._status_future = loop.create_future()

        for frame in frames:
            await self.client.write_gatt_char(WRITE_UUID, frame, response=False)
            await asyncio.sleep(0.02)  # Tiny inter-frame throttle

        if wait_response and self._status_future:
            try:
                status = await asyncio.wait_for(self._status_future, timeout=timeout)
                return status
            except asyncio.TimeoutError:
                return self._latest_status
            finally:
                self._status_future = None

        return self._latest_status

    async def power_on(self) -> Optional[ZenggeDeviceStatus]:
        return await self.send_command(ZenggePayloadBuilder.power_on(), wait_response=True)

    async def power_off(self) -> Optional[ZenggeDeviceStatus]:
        return await self.send_command(ZenggePayloadBuilder.power_off(), wait_response=True)

    async def query_status(self) -> Optional[ZenggeDeviceStatus]:
        return await self.send_command(ZenggePayloadBuilder.query_status(), wait_response=True)

    async def set_rgb(self, r: int, g: int, b: int) -> Optional[ZenggeDeviceStatus]:
        return await self.send_command(ZenggePayloadBuilder.set_rgb(r, g, b), wait_response=True)

    async def set_hsv(self, hue: int, sat: int, bri: int) -> Optional[ZenggeDeviceStatus]:
        return await self.send_command(ZenggePayloadBuilder.set_hsv(hue, sat, bri), wait_response=True)

    async def set_brightness(self, brightness: int) -> Optional[ZenggeDeviceStatus]:
        status = self._latest_status or await self.query_status()
        if status and status.channel_mode == "RGB":
            # Preserve current hue/saturation
            return await self.set_hsv(status.hue, status.saturation, brightness)
        elif status and status.channel_mode == "WHITE":
            return await self.set_cct(status.cool_white, brightness)
        else:
            # Default to White scale
            val = int((brightness / 100.0) * 255)
            return await self.send_command(ZenggePayloadBuilder.set_white(val, val), wait_response=True)

    async def set_cct(self, cct_percent: int, brightness: int = 100) -> Optional[ZenggeDeviceStatus]:
        return await self.send_command(ZenggePayloadBuilder.set_cct(cct_percent, brightness), wait_response=True)

    async def set_scene(self, mode_id: int, speed: int = 16) -> Optional[ZenggeDeviceStatus]:
        return await self.send_command(ZenggePayloadBuilder.set_scene(mode_id, speed), wait_response=True)

    async def run_animated_scene(
        self,
        scene_name: str,
        duration: float = 0.0,
        speed: int = 16,
        stop_event: Optional[asyncio.Event] = None,
    ):
        """
        Runs a software-driven high-framerate dynamic lighting scene.
        """
        name = scene_name.lower().replace("-", "_").replace(" ", "_")
        dur_msg = f"{duration}s" if duration > 0 else "Continuous (Ctrl+C to stop)"
        console.print(f"[bold cyan]▶ Starting dynamic scene:[/bold cyan] [bold green]{name}[/bold green] (Speed: {speed}, Duration: {dur_msg})")

        start_time = asyncio.get_event_loop().time()

        if name in ["rainbow", "rainbow_flow", "rainbow_fade", "spectrum"]:
            hue = 0.0
            step = 360.0 / max(15, (32 - speed) * 8)
            while True:
                if stop_event and stop_event.is_set():
                    break
                if duration > 0 and (asyncio.get_event_loop().time() - start_time) >= duration:
                    break
                hue = (hue + step) % 360
                await self.set_hsv(int(hue), 100, 100)
                await asyncio.sleep(0.05)

        elif name in ["candle", "fire", "flicker"]:
            import random
            while True:
                if stop_event and stop_event.is_set():
                    break
                if duration > 0 and (asyncio.get_event_loop().time() - start_time) >= duration:
                    break
                flicker_hue = random.randint(24, 44)
                flicker_bri = random.randint(30, 100)
                flicker_sat = random.randint(85, 100)
                await self.set_hsv(flicker_hue, flicker_sat, flicker_bri)
                await asyncio.sleep(random.uniform(0.04, 0.16))

        elif name in ["pulse", "breathing", "breath"]:
            t = 0.0
            while True:
                if stop_event and stop_event.is_set():
                    break
                if duration > 0 and (asyncio.get_event_loop().time() - start_time) >= duration:
                    break
                t += 0.08
                bri = int(55 + 45 * math.sin(t))
                hue = int((t * 25) % 360)
                await self.set_hsv(hue, 100, max(5, bri))
                await asyncio.sleep(0.05)

        elif name in ["aurora", "northern_lights"]:
            t = 0.0
            while True:
                if stop_event and stop_event.is_set():
                    break
                if duration > 0 and (asyncio.get_event_loop().time() - start_time) >= duration:
                    break
                t += 0.06
                base_hue = 130 + 85 * math.sin(t)
                bri = int(70 + 30 * math.sin(t * 1.4))
                await self.set_hsv(int(base_hue) % 360, 100, max(20, bri))
                await asyncio.sleep(0.06)

        elif name in ["police", "emergency"]:
            while True:
                if stop_event and stop_event.is_set():
                    break
                if duration > 0 and (asyncio.get_event_loop().time() - start_time) >= duration:
                    break
                for _ in range(2):
                    await self.set_hsv(0, 100, 100)
                    await asyncio.sleep(0.06)
                    await self.set_hsv(0, 100, 0)
                    await asyncio.sleep(0.04)
                for _ in range(2):
                    await self.set_hsv(240, 100, 100)
                    await asyncio.sleep(0.06)
                    await self.set_hsv(240, 100, 0)
                    await asyncio.sleep(0.04)
        else:
            console.print(f"[yellow]Unknown scene '{name}'. Available: rainbow, candle, pulse, aurora, police[/yellow]")


# ==============================================================================
# Device Discovery & UI Helpers
# ==============================================================================

async def scan_for_lamps(timeout: float = 5.0) -> list[BLEDevice]:
    """Scans for nearby BLE devices with Zengge/MagicHome characteristics or names."""
    console.print(f"[cyan]Scanning for nearby Zengge BLE lamps ({timeout}s)...[/cyan]")
    devices = await BleakScanner.discover(timeout=timeout, return_adv=True)

    found = []
    table = Table(title="Discovered BLE Devices")
    table.add_column("Name", style="green", no_wrap=True)
    table.add_column("Address / UUID", style="cyan", no_wrap=True)
    table.add_column("RSSI", style="yellow")
    table.add_column("Service UUIDs", style="magenta")

    for dev, adv in devices.values():
        name = dev.name or adv.local_name or "Unknown"
        is_zengge = False
        service_uuids = [str(u).lower() for u in adv.service_uuids]

        if "ffff" in "".join(service_uuids) or "fe00" in "".join(service_uuids):
            if "prov_" not in name.lower():
                is_zengge = True
        elif any(k in name.lower() for k in ["iotbt", "led", "bulb", "lamp", "zengge", "magichome", "hf-", "flux"]):
            is_zengge = True
        elif any(mfg_id in [0x5A, 0x5B, 0x5C, 90, 91, 92] for mfg_id in adv.manufacturer_data.keys()):
            is_zengge = True

        if is_zengge or name != "Unknown":
            table.add_row(
                f"[bold]{name}[/bold]" if is_zengge else name,
                dev.address,
                f"{adv.rssi} dBm",
                ", ".join(service_uuids[:2]) or "N/A",
            )
            if is_zengge:
                found.append(dev)

    console.print(table)
    return found


async def wait_for_lamp_and_connect(target_address: Optional[str] = None, timeout: float = 60.0) -> Optional[ZenggeLampClient]:
    """
    Actively listens for the lamp's BLE advertisement beacons as soon as it powers on,
    and immediately connects before other devices can capture the connection.
    """
    console.print(f"[bold cyan]⏳ Listening for lamp power-on beacon (up to {int(timeout)}s)...[/bold cyan]")
    console.print("[dim]Turn your lamp switch ON now![/dim]\n")

    stop_event = asyncio.Event()
    discovered: list[BLEDevice] = []

    def detection_callback(device: BLEDevice, advertisement_data):
        name = device.name or advertisement_data.local_name or ""
        service_uuids = [str(u).lower() for u in advertisement_data.service_uuids]
        is_match = False

        if target_address:
            if device.address.lower() == target_address.lower():
                is_match = True
        else:
            if "iotbt" in name.lower() or "zengge" in name.lower() or "lednet" in name.lower():
                is_match = True
            elif ("ffff" in "".join(service_uuids) or "fe00" in "".join(service_uuids)) and "prov_" not in name.lower():
                is_match = True

        if is_match and not discovered:
            console.print(f"[bold green]⚡ Detected lamp beacon:[/bold green] [white]{name or 'Zengge Lamp'}[/white] ({device.address}) RSSI={advertisement_data.rssi} dBm")
            discovered.append(device)
            stop_event.set()

    scanner = BleakScanner(detection_callback=detection_callback)
    await scanner.start()
    try:
        await asyncio.wait_for(stop_event.wait(), timeout=timeout)
    except asyncio.TimeoutError:
        console.print("[red]Timed out waiting for lamp. Did not detect BLE beacon.[/red]")
        return None
    finally:
        await scanner.stop()

    if discovered:
        client = ZenggeLampClient(discovered[0].address, target_device=discovered[0])
        connected = await client.connect(timeout=10.0)
        if connected:
            return client
    return None


def display_status_panel(status: ZenggeDeviceStatus):
    """Renders formatted device status in a rich panel."""
    p_text = "[bold green]ON[/bold green]" if status.power else "[bold red]OFF[/bold red]"
    r, g, b = status.rgb_approx
    color_box = f"rgb({r},{g},{b})"

    content = Text()
    content.append(f"Power State:   ", style="bold")
    content.append(f"{'ON' if status.power else 'OFF'}\n", style="green" if status.power else "red")
    content.append(f"Mode:          ", style="bold")
    content.append(f"{status.mode_name} (0x{status.mode_id:02X})\n", style="cyan")
    content.append(f"Channel:       ", style="bold")
    content.append(f"{status.channel_mode}\n", style="yellow")
    content.append(f"Brightness:    ", style="bold")
    content.append(f"{status.brightness}%\n", style="magenta")

    if status.channel_mode == "RGB":
        content.append(f"Hue / Sat:     ", style="bold")
        content.append(f"{status.hue}° / {status.saturation}%\n", style="white")
        content.append(f"RGB Preview:   ", style="bold")
        content.append(f"████████  #{r:02X}{g:02X}{b:02X} (RGB: {r},{g},{b})\n", style=color_box)
    else:
        content.append(f"Warm / Cold:   ", style="bold")
        content.append(f"{status.warm_white}% / {status.cool_white}%\n", style="white")

    content.append(f"\nRaw Telemetry: [dim]{status.raw_hex}[/dim]")

    console.print(Panel(content, title="[bold white]Zengge Smart Lamp Status[/bold white]", border_style="cyan"))


def parse_color_input(arg: str) -> Optional[tuple[int, int, int]]:
    """Parses color argument from hex (#FF0000), color name ('red'), or R,G,B."""
    clean = arg.strip().lower()
    if clean in COLOR_NAMES:
        return COLOR_NAMES[clean]

    # Hex match
    hex_match = re.match(r"^#?([0-9a-f]{6})$", clean)
    if hex_match:
        h = hex_match.group(1)
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))

    # Comma or space separated
    parts = re.split(r"[, ]+", clean)
    if len(parts) == 3:
        try:
            return (int(parts[0]), int(parts[1]), int(parts[2]))
        except ValueError:
            pass

    return None


def parse_scene_input(arg: str) -> Optional[int]:
    """Parses scene identifier by number (1-20, 0x25-0x2C) or alias/name."""
    clean = arg.strip().lower().replace("_", "-").replace(" ", "-")
    # Match alias or name
    for mode_id, (desc, alias) in SCENE_PRESETS.items():
        desc_clean = desc.lower().replace(" ", "-").replace("_", "-")
        if clean in [alias, alias.replace("-", ""), desc_clean, str(mode_id), hex(mode_id).lower()]:
            return mode_id

    try:
        val = int(clean, 0)
        if val in SCENE_PRESETS or 0x01 <= val <= 0x50:
            return val
    except ValueError:
        pass

    return None


# ==============================================================================
# Interactive REPL Loop
# ==============================================================================

async def run_interactive_repl(client: ZenggeLampClient):
    """Interactive command loop for direct lamp manipulation."""
    console.print("\n[bold cyan]=== Zengge Lamp Interactive REPL ===[/bold cyan]")
    console.print("[dim]Type 'help' for available commands, 'exit' or Ctrl+C to quit.[/dim]\n")

    # Fetch initial status
    status = await client.query_status()
    if status:
        display_status_panel(status)

    while True:
        try:
            line = await asyncio.get_event_loop().run_in_executor(None, lambda: input("zengge> ").strip())
        except (EOFError, KeyboardInterrupt):
            break

        if not line:
            continue

        tokens = line.split()
        cmd = tokens[0].lower()
        args = tokens[1:]

        if cmd in ["exit", "quit", "q"]:
            break

        elif cmd in ["help", "?"]:
            table = Table(title="Available REPL Commands")
            table.add_column("Command", style="cyan")
            table.add_column("Description", style="white")
            table.add_row("power <on|off>", "Toggle lamp power")
            table.add_row("on / off", "Quick power shortcut")
            table.add_row("rgb <R G B | #hex | name>", "Set color (e.g. 'rgb red', 'rgb #00ff00', 'rgb 255 100 0')")
            table.add_row("brightness <0-100>", "Set brightness percentage")
            table.add_row("cct <0-100> [brightness]", "Set color temperature (0=warm, 100=cool)")
            table.add_row("warm / cool", "Quick white temperature presets")
            table.add_row("scene <id|alias> [speed]", "Activate dynamic effect (1-31 speed)")
            table.add_row("scenes", "List all built-in scene presets")
            table.add_row("status / st", "Query and show live status")
            table.add_row("raw <hex>", "Send raw inner payload bytes")
            table.add_row("exit / quit", "Disconnect and exit")
            console.print(table)

        elif cmd == "scenes":
            table = Table(title="Preset Scene Effects")
            table.add_column("ID (Hex)", style="magenta")
            table.add_column("ID (Dec)", style="cyan")
            table.add_column("Alias", style="yellow")
            table.add_column("Description", style="green")
            for mode_id, (desc, alias) in SCENE_PRESETS.items():
                table.add_row(f"0x{mode_id:02X}", str(mode_id), alias, desc)
            console.print(table)

        elif cmd in ["power", "p"]:
            if not args or args[0].lower() in ["on", "1", "true"]:
                res = await client.power_on()
            else:
                res = await client.power_off()
            if res:
                display_status_panel(res)

        elif cmd == "on":
            res = await client.power_on()
            if res:
                display_status_panel(res)

        elif cmd == "off":
            res = await client.power_off()
            if res:
                display_status_panel(res)

        elif cmd in ["status", "st"]:
            res = await client.query_status()
            if res:
                display_status_panel(res)
            else:
                console.print("[yellow]No status response received.[/yellow]")

        elif cmd in ["rgb", "color"]:
            if not args:
                console.print("[red]Usage: rgb <R G B | #hex | color_name>[/red]")
                continue
            color_str = " ".join(args)
            rgb = parse_color_input(color_str)
            if not rgb:
                console.print(f"[red]Invalid color specification: '{color_str}'[/red]")
                continue
            res = await client.set_rgb(*rgb)
            if res:
                display_status_panel(res)

        elif cmd in ["brightness", "bri", "dim"]:
            if not args:
                console.print("[red]Usage: brightness <0-100>[/red]")
                continue
            try:
                bri = int(args[0])
                res = await client.set_brightness(bri)
                if res:
                    display_status_panel(res)
            except ValueError:
                console.print("[red]Brightness must be a number between 0 and 100[/red]")

        elif cmd in ["cct", "white"]:
            cct_val = 50
            bri_val = 100
            if args:
                try:
                    cct_val = int(args[0])
                    if len(args) > 1:
                        bri_val = int(args[1])
                except ValueError:
                    pass
            res = await client.set_cct(cct_val, bri_val)
            if res:
                display_status_panel(res)

        elif cmd == "warm":
            res = await client.set_cct(0, 100)
            if res:
                display_status_panel(res)

        elif cmd == "cool":
            res = await client.set_cct(100, 100)
            if res:
                display_status_panel(res)

        elif cmd == "scene":
            if not args:
                console.print("[red]Usage: scene <name|id> [speed 1-31] [duration_sec][/red]")
                continue
            anim_names = ["rainbow", "rainbow-flow", "rainbow-fade", "candle", "fire", "flicker", "pulse", "breathing", "aurora", "police", "emergency"]
            s_name = args[0].lower()
            speed = 16
            dur = 0.0
            if len(args) > 1:
                try:
                    speed = int(args[1])
                except ValueError:
                    pass
            if len(args) > 2:
                try:
                    dur = float(args[2])
                except ValueError:
                    pass

            if s_name in anim_names:
                await client.power_on()
                try:
                    await client.run_animated_scene(s_name, duration=dur, speed=speed)
                except (asyncio.CancelledError, KeyboardInterrupt):
                    console.print("\n[yellow]Scene stopped.[/yellow]")
            else:
                mode_id = parse_scene_input(s_name)
                if mode_id is not None:
                    await client.power_on()
                    res = await client.set_scene(mode_id, speed)
                    if res:
                        display_status_panel(res)
                else:
                    console.print(f"[red]Unknown scene: '{s_name}'. Available: rainbow, candle, pulse, aurora, police[/red]")

        elif cmd == "raw":
            if not args:
                console.print("[red]Usage: raw <hex_payload>[/red]")
                continue
            try:
                payload = bytes.fromhex("".join(args))
                res = await client.send_command(payload, wait_response=True)
                if res:
                    display_status_panel(res)
            except Exception as e:
                console.print(f"[red]Error sending raw bytes: {e}[/red]")

        else:
            console.print(f"[red]Unknown command: '{cmd}'. Type 'help' for options.[/red]")


# ==============================================================================
# Main CLI Entry Point
# ==============================================================================

async def async_main():
    parser = argparse.ArgumentParser(
        description="Standalone Python BLE Controller for Zengge/MagicHome Smart Lamp.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--mac", "-m", help="Target lamp BLE MAC address or macOS UUID")
    parser.add_argument("--scan", action="store_true", help="Scan for nearby Zengge BLE lamps")
    parser.add_argument("--power", choices=["on", "off"], help="Turn power on or off")
    parser.add_argument("--rgb", nargs="+", help="Set RGB color: R G B, #RRGGBB, or name (e.g. --rgb 255 0 0 or --rgb red)")
    parser.add_argument("--brightness", "-b", type=int, help="Set brightness (0-100)")
    parser.add_argument("--cct", type=int, help="Set color temperature (0=Warm White, 100=Cool White)")
    parser.add_argument("--scene", "-s", help="Activate dynamic scene (e.g. rainbow, candle, pulse, aurora, police) or legacy preset ID")
    parser.add_argument("--speed", type=int, default=16, help="Scene speed (1=Fastest, 31=Slowest, default: 16)")
    parser.add_argument("--duration", "-d", type=float, default=0.0, help="Duration in seconds for scene (default: 0 = continuous until Ctrl+C)")
    parser.add_argument("--status", action="store_true", help="Query and print current lamp telemetry")
    parser.add_argument("--interactive", "-i", action="store_true", help="Start interactive REPL prompt")
    parser.add_argument("--wait", "-w", action="store_true", help="Wait and listen for lamp to power on, then immediately connect")
    parser.add_argument("--timeout", type=float, default=15.0, help="Connection timeout in seconds")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose debug logging")

    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)

    if args.scan:
        await scan_for_lamps(timeout=args.timeout)
        return 0

    target_mac = args.mac
    client: Optional[ZenggeLampClient] = None

    if args.wait:
        client = await wait_for_lamp_and_connect(target_address=target_mac, timeout=max(args.timeout, 60.0))
        if not client:
            return 1
    else:
        # Auto-discover if MAC not provided
        if not target_mac:
            console.print("[yellow]No --mac address specified. Initiating discovery scan...[/yellow]")
            found = await scan_for_lamps(timeout=4.0)
            if not found:
                console.print("[bold yellow]No active lamp found in scan. Switching to live power-on listener...[/bold yellow]")
                client = await wait_for_lamp_and_connect(timeout=max(args.timeout, 60.0))
                if not client:
                    return 1
            else:
                target_mac = found[0].address
                console.print(f"[green]Using discovered device:[/green] [bold]{target_mac}[/bold] ({found[0].name})\n")
                client = ZenggeLampClient(target_mac, target_device=found[0])
                connected = await client.connect(timeout=args.timeout)
                if not connected:
                    return 1
        else:
            client = ZenggeLampClient(target_mac)
            connected = await client.connect(timeout=args.timeout)
            if not connected:
                console.print("[yellow]Direct connection failed. Retrying with live power-on listener...[/yellow]")
                client = await wait_for_lamp_and_connect(target_address=target_mac, timeout=max(args.timeout, 60.0))
                if not client:
                    return 1

    try:
        # Check if single action was requested
        executed_action = False

        if args.power:
            executed_action = True
            console.print(f"[cyan]Setting power -> {args.power.upper()}...[/cyan]")
            res = await (client.power_on() if args.power == "on" else client.power_off())
            if res:
                display_status_panel(res)

        if args.rgb:
            executed_action = True
            color_str = " ".join(args.rgb)
            rgb = parse_color_input(color_str)
            if rgb:
                console.print(f"[cyan]Setting RGB -> {rgb}...[/cyan]")
                res = await client.set_rgb(*rgb)
                if res:
                    display_status_panel(res)
            else:
                console.print(f"[red]Could not parse RGB color: '{color_str}'[/red]")

        if args.cct is not None:
            executed_action = True
            bri = args.brightness if args.brightness is not None else 100
            console.print(f"[cyan]Setting CCT -> {args.cct}% (Brightness: {bri}%)...[/cyan]")
            res = await client.set_cct(args.cct, bri)
            if res:
                display_status_panel(res)

        if args.brightness is not None and args.rgb is None and args.cct is None:
            executed_action = True
            console.print(f"[cyan]Setting brightness -> {args.brightness}%...[/cyan]")
            res = await client.set_brightness(args.brightness)
            if res:
                display_status_panel(res)

        if args.scene:
            executed_action = True
            anim_names = ["rainbow", "rainbow_flow", "rainbow-flow", "rainbow_fade", "rainbow-fade", "spectrum", "candle", "fire", "flicker", "pulse", "breathing", "aurora", "police", "emergency"]
            if args.scene.lower() in anim_names:
                await client.power_on()
                try:
                    await client.run_animated_scene(args.scene, duration=args.duration, speed=args.speed)
                except (asyncio.CancelledError, KeyboardInterrupt):
                    console.print("\n[yellow]Scene stopped.[/yellow]")
            else:
                mode_id = parse_scene_input(args.scene)
                if mode_id is not None:
                    console.print(f"[cyan]Setting scene -> {args.scene} (Speed: {args.speed})...[/cyan]")
                    await client.power_on()
                    res = await client.set_scene(mode_id, args.speed)
                    if res:
                        display_status_panel(res)
                else:
                    console.print(f"[red]Unknown scene: '{args.scene}'[/red]")

        if args.status or (not executed_action and not args.interactive):
            if not executed_action:
                console.print("[cyan]Querying device status...[/cyan]")
                res = await client.query_status()
                if res:
                    display_status_panel(res)
                else:
                    console.print("[yellow]No status response received.[/yellow]")

        if args.interactive or not executed_action:
            await run_interactive_repl(client)

    finally:
        await client.disconnect()

    return 0


def main():
    try:
        sys.exit(asyncio.run(async_main()))
    except KeyboardInterrupt:
        console.print("\n[yellow]Exiting on user interrupt.[/yellow]")
        sys.exit(0)


if __name__ == "__main__":
    main()
