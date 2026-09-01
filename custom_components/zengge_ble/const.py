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
MIN_COLOR_TEMP_KELVIN = 2700  # 100% Warm White (CCT 0%)
MAX_COLOR_TEMP_KELVIN = 6500  # 100% Cool White (CCT 100%)
DEFAULT_COLOR_TEMP_KELVIN = 4000

# Configuration entry keys
CONF_DISCOVERY_TITLE = "title"

# Timeout and retry configuration
DEFAULT_CONNECTION_TIMEOUT = 10.0
DEFAULT_COMMAND_TIMEOUT = 3.0
INTER_FRAME_DELAY = 0.02  # 20ms throttle between segmented BLE chunks

# 26 Native Hardware Scenes & Custom Presets from Companion App Tab 3
SCENE_PRESETS: dict[int, tuple[str, str]] = {
    # Custom Dynamic Animations
    0x25: ("Custom Three Color Gradient", "gradient-3"),
    0x26: ("Custom Five Color Jump", "jump-5"),
    0x27: ("Custom Colorful Breath", "colorful-breath"),
    0x28: ("Custom Heartbeat", "heartbeat"),
    0x29: ("Custom Lightning", "lightning"),
    0x2C: ("Custom Flame", "flame"),
    # Hardware Presets Row 1
    0x01: ("Preset Breathe", "breathe"),
    0x02: ("Preset Step Change", "step-change"),
    0x03: ("Preset Rhythm Change", "rhythm-change"),
    0x04: ("Preset Leisure", "leisure"),
    0x05: ("Preset Night Light", "night-light"),
    # Hardware Presets Row 2
    0x06: ("Preset Good Night", "good-night"),
    0x07: ("Preset Read", "read"),
    0x08: ("Preset Work", "work"),
    0x09: ("Preset Grassland", "grassland"),
    0x0A: ("Preset Colorful", "colorful"),
    # Hardware Presets Row 3
    0x0B: ("Preset Dazzling", "dazzling"),
    0x0C: ("Preset Gorgeous", "gorgeous"),
    0x0D: ("Preset Blue Sky", "blue-sky"),
    0x0E: ("Preset Sunflower", "sunflower"),
    0x0F: ("Preset Forest", "forest"),
    # Hardware Presets Row 4
    0x10: ("Preset Mediterranean", "mediterranean"),
    0x11: ("Preset French Style", "french-style"),
    0x12: ("Preset American Style", "american-style"),
    0x13: ("Preset Birthday", "birthday"),
    0x14: ("Preset Wedding Day", "wedding-day"),
}

# Also support short friendly aliases (e.g. "Flame", "Read", "Breathe")
SHORT_SCENE_ALIASES: dict[str, int] = {
    "Three Color Gradient": 0x25,
    "Five Color Jump": 0x26,
    "Colorful Breath": 0x27,
    "Heartbeat": 0x28,
    "Lightning": 0x29,
    "Flame": 0x2C,
    "Breathe": 0x01,
    "Step Change": 0x02,
    "Rhythm Change": 0x03,
    "Leisure": 0x04,
    "Night Light": 0x05,
    "Good Night": 0x06,
    "Read": 0x07,
    "Work": 0x08,
    "Grassland": 0x09,
    "Colorful": 0x0A,
    "Dazzling": 0x0B,
    "Gorgeous": 0x0C,
    "Blue Sky": 0x0D,
    "Sunflower": 0x0E,
    "Forest": 0x0F,
    "Mediterranean": 0x10,
    "French Style": 0x11,
    "American Style": 0x12,
    "Birthday": 0x13,
    "Wedding Day": 0x14,
}

EFFECT_LIST: list[str] = [name for name, _ in SCENE_PRESETS.values()]
EFFECT_NAME_TO_ID: dict[str, int] = {name: sid for sid, (name, _) in SCENE_PRESETS.items()}
EFFECT_NAME_TO_ID.update(SHORT_SCENE_ALIASES)
EFFECT_SLUG_TO_ID: dict[str, int] = {slug: sid for sid, (_, slug) in SCENE_PRESETS.items()}
