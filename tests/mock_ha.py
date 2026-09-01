"""Lightweight Home Assistant mock environment for standalone unit testing."""

from __future__ import annotations

import sys
import types
from enum import Enum, Flag
from typing import Any, Callable, Generic, Optional, TypeVar

T = TypeVar("T")

# Mock voluptuous if not installed
if "voluptuous" not in sys.modules:
    try:
        import voluptuous
    except ImportError:
        vol = types.ModuleType("voluptuous")

        class Schema:
            def __init__(self, schema):
                self.schema = schema

            def __call__(self, data):
                return data

        class Marker:
            def __init__(self, schema, default=None):
                self.schema = schema
                self.default = default

        class Required(Marker):
            pass

        class OptionalMarker(Marker):
            pass

        def In(container):
            return lambda v: v

        def Coerce(type_func):
            return type_func

        vol.Schema = Schema
        vol.Required = Required
        vol.Optional = OptionalMarker
        vol.In = In
        vol.Coerce = Coerce
        sys.modules["voluptuous"] = vol


def callback(func: Callable) -> Callable:
    """Decorator to mark callback functions."""
    return func


class ColorMode(str, Enum):
    UNKNOWN = "unknown"
    ONOFF = "onoff"
    BRIGHTNESS = "brightness"
    COLOR_TEMP = "color_temp"
    HS = "hs"
    XY = "xy"
    RGB = "rgb"
    RGBW = "rgbw"
    RGBWW = "rgbww"
    WHITE = "white"


class LightEntityFeature(Flag):
    EFFECT = 4
    FLASH = 8
    TRANSITION = 32


ATTR_BRIGHTNESS = "brightness"
ATTR_COLOR_TEMP_KELVIN = "color_temp_kelvin"
ATTR_HS_COLOR = "hs_color"
ATTR_RGB_COLOR = "rgb_color"
ATTR_EFFECT = "effect"
CONF_ADDRESS = "address"
CONF_NAME = "name"


class Platform(str, Enum):
    LIGHT = "light"
    SWITCH = "switch"
    SENSOR = "sensor"


class ConfigEntryNotReady(Exception):
    """Exception to indicate config entry is not ready."""
    pass


class DeviceInfo(dict):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        for k, v in kwargs.items():
            setattr(self, k, v)


class DataUpdateCoordinator(Generic[T]):
    def __init__(self, hass, logger, name, update_interval=None):
        self.hass = hass
        self.logger = logger
        self.name = name
        self.update_interval = update_interval
        self.data: Optional[T] = None
        self._listeners = []

    def async_set_updated_data(self, data: T):
        self.data = data
        for listener in list(self._listeners):
            listener()

    def async_add_listener(self, listener):
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener) if listener in self._listeners else None

    async def async_config_entry_first_refresh(self):
        pass


class CoordinatorEntity(Generic[T]):
    def __init__(self, coordinator: T):
        self.coordinator = coordinator

    @property
    def available(self) -> bool:
        return self.coordinator.data is not None


class LightEntity:
    _attr_has_entity_name = True
    _attr_name = None
    _attr_unique_id = None
    _attr_supported_color_modes = set()
    _attr_supported_features = LightEntityFeature(0)
    _attr_min_color_temp_kelvin = 2700
    _attr_max_color_temp_kelvin = 6500
    _attr_effect_list = []

    @property
    def unique_id(self) -> Optional[str]:
        return self._attr_unique_id

    def async_write_ha_state(self):
        pass


class ConfigEntry:
    def __init__(self, entry_id="test_entry_id", unique_id="AA:BB:CC:DD:EE:FF", title="Test Light", data=None):
        self.entry_id = entry_id
        self.unique_id = unique_id
        self.title = title
        self.data = data or {CONF_ADDRESS: unique_id, CONF_NAME: title}
        self._on_unload = []

    def async_on_unload(self, func):
        self._on_unload.append(func)


class ConfigFlow:
    VERSION = 1

    def __init_subclass__(cls, domain: str | None = None, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        cls.DOMAIN = domain

    def __init__(self):
        self.hass = None
        self.context = {}
        self.unique_id = None

    async def async_set_unique_id(self, unique_id, raise_on_progress=True):
        self.unique_id = unique_id

    def _abort_if_unique_id_configured(self):
        pass

    def _async_current_ids(self):
        return set()

    def async_create_entry(self, title, data):
        return {"type": "create_entry", "title": title, "data": data}

    def async_show_form(self, step_id, data_schema=None, errors=None, description_placeholders=None):
        return {
            "type": "form",
            "step_id": step_id,
            "data_schema": data_schema,
            "errors": errors or {},
            "description_placeholders": description_placeholders or {},
        }


class BluetoothServiceInfoBleak:
    def __init__(self, name="IOTBT537", address="AA:BB:CC:DD:EE:FF", service_uuids=None, rssi=-60, device=None):
        self.name = name
        self.address = address
        self.service_uuids = service_uuids or ["0000ffff-0000-1000-8000-00805f9b34fb"]
        self.rssi = rssi
        self.device = device


class BluetoothScanningMode(Enum):
    ACTIVE = "active"
    PASSIVE = "passive"


class BluetoothCallbackMatcher:
    def __init__(self, address=None, connectable=True):
        self.address = address
        self.connectable = connectable


# Mock modules installation in sys.modules
def install_mock_ha():
    ha = types.ModuleType("homeassistant")
    ha_core = types.ModuleType("homeassistant.core")
    ha_core.HomeAssistant = object
    ha_core.callback = callback
    ha.core = ha_core

    ha_const = types.ModuleType("homeassistant.const")
    ha_const.CONF_ADDRESS = CONF_ADDRESS
    ha_const.CONF_NAME = CONF_NAME
    ha_const.Platform = Platform
    ha_const.STATE_ON = "on"
    ha_const.STATE_OFF = "off"
    ha.const = ha_const

    ha_exceptions = types.ModuleType("homeassistant.exceptions")
    ha_exceptions.ConfigEntryNotReady = ConfigEntryNotReady
    ha.exceptions = ha_exceptions

    ha_data_entry_flow = types.ModuleType("homeassistant.data_entry_flow")
    ha_data_entry_flow.FlowResult = dict
    ha.data_entry_flow = ha_data_entry_flow

    ha_config_entries = types.ModuleType("homeassistant.config_entries")
    ha_config_entries.ConfigEntry = ConfigEntry
    ha_config_entries.ConfigFlow = ConfigFlow
    ha_config_entries.ConfigFlowResult = dict
    ha.config_entries = ha_config_entries

    ha_helpers = types.ModuleType("homeassistant.helpers")
    ha_helpers_update = types.ModuleType("homeassistant.helpers.update_coordinator")
    ha_helpers_update.DataUpdateCoordinator = DataUpdateCoordinator
    ha_helpers_update.CoordinatorEntity = CoordinatorEntity
    ha_helpers_update.UpdateFailed = Exception
    ha_helpers.update_coordinator = ha_helpers_update

    ha_helpers_restore = types.ModuleType("homeassistant.helpers.restore_state")
    class RestoreEntity:
        async def async_get_last_state(self):
            return None
        async def async_added_to_hass(self):
            pass
    ha_helpers_restore.RestoreEntity = RestoreEntity
    ha_helpers.restore_state = ha_helpers_restore

    ha_helpers_dev = types.ModuleType("homeassistant.helpers.device_registry")
    ha_helpers_dev.DeviceInfo = DeviceInfo
    ha_helpers.device_registry = ha_helpers_dev

    ha_helpers_entity_platform = types.ModuleType("homeassistant.helpers.entity_platform")
    ha_helpers_entity_platform.AddEntitiesCallback = Callable
    ha_helpers.entity_platform = ha_helpers_entity_platform
    ha.helpers = ha_helpers

    ha_components = types.ModuleType("homeassistant.components")
    ha_components_light = types.ModuleType("homeassistant.components.light")
    ha_components_light.LightEntity = LightEntity
    ha_components_light.ColorMode = ColorMode
    ha_components_light.LightEntityFeature = LightEntityFeature
    ha_components_light.ATTR_BRIGHTNESS = ATTR_BRIGHTNESS
    ha_components_light.ATTR_COLOR_TEMP_KELVIN = ATTR_COLOR_TEMP_KELVIN
    ha_components_light.ATTR_HS_COLOR = ATTR_HS_COLOR
    ha_components_light.ATTR_RGB_COLOR = ATTR_RGB_COLOR
    ha_components_light.ATTR_EFFECT = ATTR_EFFECT
    ha_components.light = ha_components_light

    ha_components_bt = types.ModuleType("homeassistant.components.bluetooth")
    ha_components_bt.BluetoothServiceInfoBleak = BluetoothServiceInfoBleak
    ha_components_bt.BluetoothScanningMode = BluetoothScanningMode
    ha_components_bt.async_discovered_service_info = lambda hass, connectable=True: []
    ha_components_bt.async_ble_device_from_address = lambda hass, addr, connectable=True: None
    ha_components_bt.async_register_callback = lambda hass, cb, matcher, mode: lambda: None

    ha_components_bt_match = types.ModuleType("homeassistant.components.bluetooth.match")
    ha_components_bt_match.BluetoothCallbackMatcher = BluetoothCallbackMatcher
    ha_components_bt.match = ha_components_bt_match

    ha_components.bluetooth = ha_components_bt
    ha.components = ha_components

    sys.modules["homeassistant"] = ha
    sys.modules["homeassistant.core"] = ha_core
    sys.modules["homeassistant.const"] = ha_const
    sys.modules["homeassistant.exceptions"] = ha_exceptions
    sys.modules["homeassistant.data_entry_flow"] = ha_data_entry_flow
    sys.modules["homeassistant.config_entries"] = ha_config_entries
    sys.modules["homeassistant.helpers"] = ha_helpers
    sys.modules["homeassistant.helpers.update_coordinator"] = ha_helpers_update
    sys.modules["homeassistant.helpers.restore_state"] = ha_helpers_restore
    sys.modules["homeassistant.helpers.device_registry"] = ha_helpers_dev
    sys.modules["homeassistant.helpers.entity_platform"] = ha_helpers_entity_platform
    sys.modules["homeassistant.components"] = ha_components
    sys.modules["homeassistant.components.light"] = ha_components_light
    sys.modules["homeassistant.components.bluetooth"] = ha_components_bt
    sys.modules["homeassistant.components.bluetooth.match"] = ha_components_bt_match


# Auto-install when imported
install_mock_ha()
