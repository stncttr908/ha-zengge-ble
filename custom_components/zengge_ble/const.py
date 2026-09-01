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

# Dynamic Hardware Animations (executed directly on lamp microcontroller)
DYNAMIC_SCENES: dict[str, dict[str, int | str]] = {
    "Seven Color Cross Fade": {"type": "magichome", "mode_id": 0x25, "speed": 16},
    "Seven Color Jumping": {"type": "magichome", "mode_id": 0x38, "speed": 16},
    "Seven Color Strobe": {"type": "magichome", "mode_id": 0x30, "speed": 16},
    "Red Gradual Change": {"type": "magichome", "mode_id": 0x26, "speed": 16},
    "Green Gradual Change": {"type": "magichome", "mode_id": 0x27, "speed": 16},
    "Blue Gradual Change": {"type": "magichome", "mode_id": 0x28, "speed": 16},
    "Yellow Gradual Change": {"type": "magichome", "mode_id": 0x29, "speed": 16},
    "Cyan Gradual Change": {"type": "magichome", "mode_id": 0x2A, "speed": 16},
    "Purple Gradual Change": {"type": "magichome", "mode_id": 0x2B, "speed": 16},
    "White Gradual Change": {"type": "magichome", "mode_id": 0x2C, "speed": 16},
    "Red/Green Cross Fade": {"type": "magichome", "mode_id": 0x2D, "speed": 16},
    "Red/Blue Cross Fade": {"type": "magichome", "mode_id": 0x2E, "speed": 16},
    "Green/Blue Cross Fade": {"type": "magichome", "mode_id": 0x2F, "speed": 16},
    "Flame": {"type": "hagall", "mode_id": 0x2C, "speed": 16},
    "Three Color Gradient": {"type": "hagall", "mode_id": 0x25, "speed": 16},
    "Five Color Jump": {"type": "hagall", "mode_id": 0x26, "speed": 16},
    "Colorful Breath": {"type": "hagall", "mode_id": 0x27, "speed": 16},
    "Heartbeat": {"type": "hagall", "mode_id": 0x28, "speed": 16},
    "Lightning": {"type": "hagall", "mode_id": 0x29, "speed": 16},
}

# Curated Mood & Ambience Presets (from MagicHome Companion App)
AMBIENCE_PRESETS: dict[str, dict[str, int | tuple[int, int, int]]] = {
    "Read": {"type": "cct", "cct_pct": 55, "bri": 100},
    "Work": {"type": "cct", "cct_pct": 90, "bri": 100},
    "Leisure": {"type": "cct", "cct_pct": 15, "bri": 80},
    "Night Light": {"type": "cct", "cct_pct": 0, "bri": 10},
    "Good Night": {"type": "cct", "cct_pct": 0, "bri": 30},
    "Grassland": {"type": "hsv", "hue": 120, "sat": 70, "bri": 80},
    "Blue Sky": {"type": "hsv", "hue": 205, "sat": 80, "bri": 90},
    "Sunflower": {"type": "hsv", "hue": 45, "sat": 90, "bri": 100},
    "Forest": {"type": "hsv", "hue": 145, "sat": 85, "bri": 75},
    "Mediterranean": {"type": "hsv", "hue": 185, "sat": 75, "bri": 85},
    "French Style": {"type": "hsv", "hue": 330, "sat": 60, "bri": 80},
    "American Style": {"type": "hsv", "hue": 225, "sat": 90, "bri": 90},
}

# Reverse-engineered mode mapping for telemetry decoding
SCENE_PRESETS: dict[int, tuple[str, str]] = {
    0x25: ("Three Color Gradient", "gradient-3"),
    0x26: ("Five Color Jump", "jump-5"),
    0x27: ("Colorful Breath", "colorful-breath"),
    0x28: ("Heartbeat", "heartbeat"),
    0x29: ("Lightning", "lightning"),
    0x2C: ("Flame", "flame"),
    0x30: ("Seven Color Strobe", "strobe-7"),
    0x38: ("Seven Color Jumping", "jump-7"),
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
}

# Combined Effect List
EFFECT_LIST: list[str] = list(DYNAMIC_SCENES.keys()) + list(AMBIENCE_PRESETS.keys())
EFFECT_NAME_TO_ID: dict[str, int] = {name: sid for sid, (name, _) in SCENE_PRESETS.items()}
EFFECT_SLUG_TO_ID: dict[str, int] = {slug: sid for sid, (_, slug) in SCENE_PRESETS.items()}
