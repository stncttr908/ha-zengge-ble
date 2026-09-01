"""Light platform support for Zengge HagallBjarkan BLE Light."""

from __future__ import annotations

import logging
from typing import Any, Optional

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_EFFECT,
    ATTR_HS_COLOR,
    ATTR_RGB_COLOR,
    ColorMode,
    LightEntity,
    LightEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    EFFECT_LIST,
    EFFECT_NAME_TO_ID,
    EFFECT_SLUG_TO_ID,
    MAX_COLOR_TEMP_KELVIN,
    MIN_COLOR_TEMP_KELVIN,
    SCENE_PRESETS,
)
from .coordinator import ZenggeDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Zengge BLE light platform from a config entry."""
    coordinator: ZenggeDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([ZenggeHBLightEntity(coordinator, entry)])


class ZenggeHBLightEntity(CoordinatorEntity[ZenggeDataUpdateCoordinator], LightEntity):
    """Representation of a Zengge BLE Smart Lamp entity."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_supported_color_modes = {ColorMode.HS, ColorMode.COLOR_TEMP}
    _attr_supported_features = LightEntityFeature.EFFECT
    _attr_min_color_temp_kelvin = MIN_COLOR_TEMP_KELVIN
    _attr_max_color_temp_kelvin = MAX_COLOR_TEMP_KELVIN
    _attr_effect_list = EFFECT_LIST

    def __init__(
        self,
        coordinator: ZenggeDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the light entity."""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.unique_id or coordinator.ble_device.address}_light"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device registry information."""
        address = self._entry.unique_id or self.coordinator.ble_device.address
        title = self._entry.title or self.coordinator.ble_device.name or f"Zengge Lamp {address}"
        return DeviceInfo(
            identifiers={(DOMAIN, address)},
            name=title,
            manufacturer="Zengge / MagicHome",
            model="HagallBjarkan Smart Lamp",
            hw_version="BLE 5.0",
        )

    @property
    def is_on(self) -> Optional[bool]:
        """Return true if light is on."""
        if self.coordinator.data is not None:
            return self.coordinator.data.power
        return None

    @property
    def brightness(self) -> Optional[int]:
        """Return the brightness of this light between 0..255."""
        if self.coordinator.data is not None:
            return int(round((self.coordinator.data.brightness / 100.0) * 255))
        return None

    @property
    def color_mode(self) -> ColorMode:
        """Return the current active color mode."""
        if self.coordinator.data is not None:
            if self.coordinator.data.channel_mode == "WHITE":
                return ColorMode.COLOR_TEMP
            return ColorMode.HS
        return ColorMode.HS

    @property
    def hs_color(self) -> Optional[tuple[float, float]]:
        """Return the hue and saturation color value [float, float] (0..360, 0..100)."""
        if self.coordinator.data is not None and self.coordinator.data.channel_mode == "RGB":
            return (float(self.coordinator.data.hue), float(self.coordinator.data.saturation))
        return None

    @property
    def color_temp_kelvin(self) -> Optional[int]:
        """Return the CT color value in Kelvin."""
        if self.coordinator.data is not None and self.coordinator.data.channel_mode == "WHITE":
            cct_pct = self.coordinator.data.cool_white
            kelvin = MIN_COLOR_TEMP_KELVIN + (cct_pct / 100.0) * (MAX_COLOR_TEMP_KELVIN - MIN_COLOR_TEMP_KELVIN)
            return int(round(kelvin))
        return None

    @property
    def effect(self) -> Optional[str]:
        """Return the current active effect scene name."""
        if self.coordinator.data is not None and self.coordinator.data.is_scene_mode:
            preset = SCENE_PRESETS.get(self.coordinator.data.mode_id)
            if preset:
                return preset[0]
        return None

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on with optional attributes."""
        device = self.coordinator.device
        new_status = None

        if ATTR_EFFECT in kwargs:
            effect_name = kwargs[ATTR_EFFECT]
            scene_id = EFFECT_NAME_TO_ID.get(effect_name) or EFFECT_SLUG_TO_ID.get(effect_name.lower())
            if scene_id is not None:
                _LOGGER.debug("Activating scene %s (ID: 0x%02X)", effect_name, scene_id)
                new_status = await device.set_scene(scene_id)
            else:
                _LOGGER.warning("Unknown effect requested: %s", effect_name)
                new_status = await device.power_on()

        elif ATTR_HS_COLOR in kwargs:
            hue, sat = kwargs[ATTR_HS_COLOR]
            if ATTR_BRIGHTNESS in kwargs:
                bri = max(1, int(round((kwargs[ATTR_BRIGHTNESS] / 255.0) * 100)))
            else:
                bri = self.coordinator.data.brightness if self.coordinator.data else 100
            _LOGGER.debug("Setting HS color: Hue=%.1f, Sat=%.1f, Bri=%d%%", hue, sat, bri)
            new_status = await device.set_hsv(int(round(hue)) % 360, int(round(sat)), bri)

        elif ATTR_RGB_COLOR in kwargs:
            r, g, b = kwargs[ATTR_RGB_COLOR]
            _LOGGER.debug("Setting RGB color: (%d, %d, %d)", r, g, b)
            new_status = await device.set_rgb(r, g, b)

        elif ATTR_COLOR_TEMP_KELVIN in kwargs:
            kelvin = kwargs[ATTR_COLOR_TEMP_KELVIN]
            clamped_kelvin = max(MIN_COLOR_TEMP_KELVIN, min(MAX_COLOR_TEMP_KELVIN, kelvin))
            cct_pct = int(round(((clamped_kelvin - MIN_COLOR_TEMP_KELVIN) / (MAX_COLOR_TEMP_KELVIN - MIN_COLOR_TEMP_KELVIN)) * 100))
            if ATTR_BRIGHTNESS in kwargs:
                bri = max(1, int(round((kwargs[ATTR_BRIGHTNESS] / 255.0) * 100)))
            else:
                bri = self.coordinator.data.brightness if self.coordinator.data else 100
            _LOGGER.debug("Setting CCT: Kelvin=%d -> %d%%, Bri=%d%%", clamped_kelvin, cct_pct, bri)
            new_status = await device.set_cct(cct_pct, bri)

        elif ATTR_BRIGHTNESS in kwargs:
            bri_pct = max(1, int(round((kwargs[ATTR_BRIGHTNESS] / 255.0) * 100)))
            _LOGGER.debug("Setting brightness: %d%%", bri_pct)
            new_status = await device.set_brightness(bri_pct)

        else:
            _LOGGER.debug("Turning lamp ON")
            new_status = await device.power_on()

        if new_status is not None:
            self.coordinator.async_set_updated_data(new_status)
        else:
            self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the light off."""
        _LOGGER.debug("Turning lamp OFF")
        new_status = await self.coordinator.device.power_off()
        if new_status is not None:
            self.coordinator.async_set_updated_data(new_status)
        else:
            self.async_write_ha_state()
