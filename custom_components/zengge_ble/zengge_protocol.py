"""Protocol engine and device wrapper for Zengge HagallBjarkan BLE devices."""

from __future__ import annotations

import asyncio
import colorsys
import json
import logging
from dataclasses import dataclass
from typing import Any, Callable, Optional

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.backends.device import BLEDevice
from bleak.exc import BleakError

from .const import (
    CMD_ID_APP,
    DEFAULT_COMMAND_TIMEOUT,
    DEFAULT_CONNECTION_TIMEOUT,
    INTER_FRAME_DELAY,
    MARKER_MIN_VALUE,
    NOTIFY_UUID,
    SCENE_PRESETS,
    WRITE_UUID,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class UpperTransportLayer:
    """Represents an application-level transport packet."""

    ack: bool = False
    protect: bool = False
    type: int = 0
    seq: int = 1
    cmd_id: int = CMD_ID_APP
    payload: bytes = b""


class LowerTransportLayerEncoder:
    """Encapsulates upper payloads into Lower Transport Layer frames."""

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
        """Encapsulate upper payload into one or more Lower Transport Layer frame chunks."""
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
    """Reassembles single and segmented frames into UpperTransportLayer."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
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


@dataclass
class ZenggeDeviceStatus:
    """Parsed lamp telemetry state from 26-byte status payload."""

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

    @property
    def is_scene_mode(self) -> bool:
        """Returns True if the current operating mode is a preset scene."""
        return self.mode_id in SCENE_PRESETS

    @classmethod
    def from_hex_payload(cls, hex_str: str) -> Optional[ZenggeDeviceStatus]:
        """Parses 26-byte status payload (e.g. 'EA8100000E0A23610240F0006464000000000000000000000000')."""
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
                r_f, g_f, b_f = colorsys.hsv_to_rgb(hue / 360.0, saturation / 100.0, max(0.01, brightness / 100.0))
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
        except Exception as err:
            _LOGGER.debug("Failed to parse status hex %s: %s", hex_str, err)
            return None


class ZenggePayloadBuilder:
    """Builds inner payloads for Zengge HagallBjarkan commands."""

    @staticmethod
    def _checksum(payload: bytes) -> int:
        return sum(payload) & 0xFF

    @classmethod
    def power_on(cls) -> bytes:
        return bytes([0x71, 0x23])

    @classmethod
    def power_off(cls) -> bytes:
        return bytes([0x71, 0x24])

    @classmethod
    def query_status(cls) -> bytes:
        return bytes([0x71, 0x23])

    @classmethod
    def set_rgb(cls, r: int, g: int, b: int) -> bytes:
        """Converts RGB to HagallBjarkan HSV format (0xA1)."""
        r_f = max(0, min(255, int(r))) / 255.0
        g_f = max(0, min(255, int(g))) / 255.0
        b_f = max(0, min(255, int(b))) / 255.0
        h, s, v = colorsys.rgb_to_hsv(r_f, g_f, b_f)
        hue_deg = int(round(h * 360)) % 360
        sat_pct = int(round(s * 100))
        bri_pct = int(round(v * 100))
        if bri_pct == 0:
            bri_pct = 1
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
    def set_cct(cls, cct_percent: int, brightness: int = 100) -> bytes:
        """Sets color temperature using standard MagicHome WW/CW PWM channels."""
        cct_pct = max(0, min(100, int(cct_percent)))
        bri_pct = max(1, min(100, int(brightness)))
        
        # Balance Warm White (0% CCT) vs Cool White (100% CCT)
        cct_ratio = cct_pct / 100.0
        bri_factor = (bri_pct / 100.0) * 255.0
        warm = int(round((1.0 - cct_ratio) * bri_factor))
        cold = int(round(cct_ratio * bri_factor))
        
        return cls.set_white(warm, cold)

    @classmethod
    def set_white(cls, warm: int, cold: int) -> bytes:
        warm = max(0, min(255, int(warm)))
        cold = max(0, min(255, int(cold)))
        cmd = bytearray([0x31, 0x00, 0x00, 0x00, warm, cold, 0x0F])
        cmd.append(cls._checksum(cmd))
        return bytes(cmd)

    @classmethod
    def set_scene(cls, scene_id: int, speed: int = 16) -> bytes:
        """Constructs a HagallBjarkan native firmware scene activation frame (0xE0 0x02 0x00 ...)."""
        speed_val = max(1, min(31, int(speed)))
        return bytes([0xE0, 0x02, 0x00, scene_id & 0xFF, speed_val, 0xFF])


class ZenggeLampDevice:
    """Asynchronous device controller interfacing with BleakClient and BLEDevice."""

    def __init__(self, ble_device: Optional[BLEDevice] = None, address: Optional[str] = None) -> None:
        self._ble_device = ble_device
        self._address = (ble_device.address if ble_device else address) or ""
        self.client: Optional[BleakClient] = None
        self._write_char: Optional[BleakGATTCharacteristic] = None
        self._notify_char: Optional[BleakGATTCharacteristic] = None
        self._seq = 1
        self._decoder = LowerTransportLayerDecoder()
        self._status_future: Optional[asyncio.Future[ZenggeDeviceStatus]] = None
        self._latest_status: Optional[ZenggeDeviceStatus] = None
        self._callbacks: list[Callable[[ZenggeDeviceStatus], None]] = []
        self._lock = asyncio.Lock()

    @property
    def address(self) -> str:
        return self._address

    @property
    def name(self) -> str:
        if self._ble_device and self._ble_device.name:
            return self._ble_device.name
        return f"Zengge Lamp {self._address}"

    @property
    def is_connected(self) -> bool:
        return self.client is not None and self.client.is_connected

    @property
    def status(self) -> Optional[ZenggeDeviceStatus]:
        return self._latest_status

    @property
    def next_seq(self) -> int:
        s = self._seq
        self._seq = (self._seq + 1) & 0xFF
        if self._seq == 0:
            self._seq = 1
        return s

    def set_ble_device(self, ble_device: BLEDevice) -> None:
        """Update underlying BLEDevice object (e.g., when advertisement updates from proxy)."""
        self._ble_device = ble_device
        self._address = ble_device.address

    def register_status_callback(self, cb: Callable[[ZenggeDeviceStatus], None]) -> Callable[[], None]:
        """Register a callback for telemetry updates and return an unregister function."""
        self._callbacks.append(cb)
        return lambda: self.unregister_status_callback(cb)

    def unregister_status_callback(self, cb: Callable[[ZenggeDeviceStatus], None]) -> None:
        """Remove a previously registered status callback."""
        if cb in self._callbacks:
            self._callbacks.remove(cb)

    def _resolve_gatt_characteristics(self) -> bool:
        """Dynamically resolve write and notify characteristics across 16-bit and 128-bit UUID formats."""
        if not self.client or not self.client.services:
            return False

        self._write_char = None
        self._notify_char = None

        for service in self.client.services:
            for char in service.characteristics:
                uuid_str = str(char.uuid).lower()
                
                # Check for write characteristic (FF01 or write properties on FFFF service)
                if "ff01" in uuid_str:
                    self._write_char = char
                elif not self._write_char and any(p in char.properties for p in ("write-without-response", "write")):
                    if "ffff" in str(service.uuid).lower():
                        self._write_char = char

                # Check for notify characteristic (FF02 or notify properties on FFFF service)
                if "ff02" in uuid_str:
                    self._notify_char = char
                elif not self._notify_char and "notify" in char.properties:
                    if "ffff" in str(service.uuid).lower():
                        self._notify_char = char

        _LOGGER.debug(
            "Resolved GATT on %s: write_char=%s, notify_char=%s",
            self._address,
            self._write_char.uuid if self._write_char else "None",
            self._notify_char.uuid if self._notify_char else "None",
        )
        return self._write_char is not None

    async def connect(self, timeout: float = DEFAULT_CONNECTION_TIMEOUT) -> bool:
        """Connects to the lamp and enables telemetry notifications."""
        async with self._lock:
            if self.is_connected:
                return True

            target: BLEDevice | str = self._ble_device if self._ble_device is not None else self._address
            if not target:
                _LOGGER.error("Cannot connect: No BLEDevice or address specified")
                return False

            _LOGGER.debug("Connecting to Zengge lamp %s (timeout=%.1fs)", self._address, timeout)
            try:
                self.client = BleakClient(target, timeout=timeout)
                await self.client.connect()

                if not self.client.is_connected:
                    _LOGGER.warning("Failed to establish BLE connection to %s", self._address)
                    return False

                # Resolve write and notify characteristics dynamically
                self._resolve_gatt_characteristics()

                # Subscribe to notifications if notify characteristic exists
                if self._notify_char:
                    try:
                        await self.client.start_notify(self._notify_char, self._on_notification)
                        _LOGGER.debug("Subscribed to telemetry notifications (%s) on %s", self._notify_char.uuid, self._address)
                    except Exception as notif_err:
                        _LOGGER.debug("Notification subscription on %s: %s", self._address, notif_err)
                else:
                    # Fallback subscription attempt on NOTIFY_UUID
                    try:
                        await self.client.start_notify(NOTIFY_UUID, self._on_notification)
                    except Exception:
                        pass

                return True
            except Exception as err:
                _LOGGER.error("BLE connection error on %s: %s", self._address, err)
                if self.client:
                    try:
                        await self.client.disconnect()
                    except Exception:
                        pass
                    self.client = None
                return False

    async def disconnect(self) -> None:
        """Disconnects cleanly from the lamp."""
        async with self._lock:
            if self.client and self.client.is_connected:
                if self._notify_char:
                    try:
                        await self.client.stop_notify(self._notify_char)
                    except Exception:
                        pass
                try:
                    await self.client.disconnect()
                except Exception:
                    pass
            self.client = None
            self._write_char = None
            self._notify_char = None

    def _on_notification(self, sender: Any, data: bytearray) -> None:
        """Handle incoming GATT notifications on 0xFF02."""
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
                    for cb in list(self._callbacks):
                        try:
                            cb(status)
                        except Exception as cb_err:
                            _LOGGER.error("Error in status callback: %s", cb_err)
            except Exception as parse_err:
                _LOGGER.debug("Error parsing notification JSON: %s", parse_err)

    async def send_command(
        self,
        payload: bytes,
        wait_response: bool = False,
        timeout: float = DEFAULT_COMMAND_TIMEOUT,
    ) -> Optional[ZenggeDeviceStatus]:
        """Wrap inner payload into transport frames and transmit over write characteristic."""
        if not self.is_connected or self.client is None:
            connected = await self.connect()
            if not connected or self.client is None:
                raise BleakError(f"Device {self._address} not connected")

        # Ensure write characteristic is resolved
        if not self._write_char:
            self._resolve_gatt_characteristics()

        char_specifier = self._write_char or WRITE_UUID

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
            await self.client.write_gatt_char(char_specifier, frame, response=False)
            if len(frames) > 1:
                await asyncio.sleep(INTER_FRAME_DELAY)

        if wait_response and self._status_future:
            try:
                status = await asyncio.wait_for(self._status_future, timeout=timeout)
                return status
            except asyncio.TimeoutError:
                _LOGGER.debug("Timed out waiting for response on %s; returning cached state", self._address)
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

    async def set_hs(self, hue: float, saturation: float, brightness: Optional[int] = None) -> Optional[ZenggeDeviceStatus]:
        bri = brightness if brightness is not None else (self._latest_status.brightness if self._latest_status else 100)
        return await self.set_hsv(int(round(hue)) % 360, int(round(saturation)), int(round(bri)))

    async def set_cct(self, cct_percent: int, brightness: int = 100) -> Optional[ZenggeDeviceStatus]:
        return await self.send_command(ZenggePayloadBuilder.set_cct(cct_percent, brightness), wait_response=True)

    async def set_brightness(self, brightness_percent: int) -> Optional[ZenggeDeviceStatus]:
        status = self._latest_status or await self.query_status()
        if status and status.channel_mode == "RGB":
            return await self.set_hsv(status.hue, status.saturation, brightness_percent)
        elif status and status.channel_mode == "WHITE":
            return await self.set_cct(status.cool_white, brightness_percent)
        else:
            val = int((brightness_percent / 100.0) * 255)
            return await self.send_command(ZenggePayloadBuilder.set_white(val, val), wait_response=True)

    async def set_scene(self, scene_id: int, speed: int = 16) -> Optional[ZenggeDeviceStatus]:
        return await self.send_command(ZenggePayloadBuilder.set_scene(scene_id, speed), wait_response=True)
