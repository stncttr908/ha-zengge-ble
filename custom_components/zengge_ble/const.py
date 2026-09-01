"""Constants for the Zengge HagallBjarkan BLE Light integration."""

from __future__ import annotations

DOMAIN = "zengge_ble"

# GATT Service and Characteristic UUIDs
SERVICE_UUID = "0000ffff-0000-1000-8000-00805f9b34fb"
WRITE_UUID = "0000ff01-0000-1000-8000-00805f9b34fb"
NOTIFY_UUID = "0000ff02-0000-1000-8000-00805f9b34fb"

OTA_SERVICE_UUID = "0000fe00-0000-1000-8000-00805f9b34fb"
OTA_WRITE_UUID = "0000ff11-0000-1000-8000-00805f9b34fb"
OTA_NOTIFY_UUID = "0000ff22-0000-1000-8000-00805f9b34fb"

# Transport Protocol Identifiers
CMD_ID_APP = 0x0A
CMD_ID_NOTIF = 0x0C
MARKER_MIN_VALUE = 0x8000  # 16-bit Short.MIN_VALUE marker (0x8000 / -32768)

# Color Temperature Limits (in Kelvin)
MIN_COLOR_TEMP_KELVIN = 2700  # 100% Warm White
MAX_COLOR_TEMP_KELVIN = 6500  # 100% Cool White
DEFAULT_COLOR_TEMP_KELVIN = 4000

# Configuration entry keys
CONF_DISCOVERY_TITLE = "title"

# Timeout and retry configuration
DEFAULT_CONNECTION_TIMEOUT = 10.0
DEFAULT_COMMAND_TIMEOUT = 3.0
INTER_FRAME_DELAY = 0.02  # 20ms throttle between segmented BLE chunks

# Reverse-engineered HagallBjarkan Firmware Native Preset Scenes (0xE0 0x02 0x00 <ID> FF FF)
# Map: SceneID (int) -> (Display Name, Slug/Alias)
SCENE_PRESETS: dict[int, tuple[str, str]] = {
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

# Lookup maps
EFFECT_LIST: list[str] = [name for name, _ in SCENE_PRESETS.values()]
EFFECT_NAME_TO_ID: dict[str, int] = {name: sid for sid, (name, _) in SCENE_PRESETS.items()}
EFFECT_SLUG_TO_ID: dict[str, int] = {slug: sid for sid, (_, slug) in SCENE_PRESETS.items()}
