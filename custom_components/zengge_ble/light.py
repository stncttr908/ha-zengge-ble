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
from homeassistant.const import STATE_ON
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
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


class ZenggeHBLightEntity(CoordinatorEntity[ZenggeDataUpdateCoordinator], LightEntity, RestoreEntity):
    """Representation of a Zengge HagallBjarkan BLE Light entity."""

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
        self._optimistic_is_on: bool = False
        self._optimistic_brightness: int = 255
        self._optimistic_hs: tuple[float, float] = (0.0, 0.0)
        self._optimistic_cct: int = 4000
        self._optimistic_effect: Optional[str] = None
        self._optimistic_mode: ColorMode = ColorMode.COLOR_TEMP

    async def async_added_to_hass(self) -> None:
        """Restore previous state on reload or boot."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state and self.coordinator.data is None:
            self._optimistic_is_on = (last_state.state == STATE_ON)
            if last_state.attributes.get(ATTR_BRIGHTNESS) is not None:
                self._optimistic_brightness = last_state.attributes[ATTR_BRIGHTNESS]
            if last_state.attributes.get(ATTR_COLOR_TEMP_KELVIN) is not None:
                self._optimistic_cct = last_state.attributes[ATTR_COLOR_TEMP_KELVIN]
                self._optimistic_mode = ColorMode.COLOR_TEMP
            elif last_state.attributes.get(ATTR_HS_COLOR) is not None:
                self._optimistic_hs = tuple(last_state.attributes[ATTR_HS_COLOR])
                self._optimistic_mode = ColorMode.HS
            if last_state.attributes.get(ATTR_EFFECT) is not None:
                self._optimistic_effect = last_state.attributes[ATTR_EFFECT]

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
    def is_on(self) -> bool:
        """Return true if light is on."""
        if self.coordinator.data is not None:
            return self.coordinator.data.power
        return self._optimistic_is_on

    @property
    def brightness(self) -> int:
        """Return the brightness of this light between 0..255."""
        if self.coordinator.data is not None:
            return int(round((self.coordinator.data.brightness / 100.0) * 255))
        return self._optimistic_brightness

    @property
    def color_mode(self) -> ColorMode:
        """Return the current active color mode."""
        if self.coordinator.data is not None:
            if self.coordinator.data.channel_mode == "WHITE":
                return ColorMode.COLOR_TEMP
            return ColorMode.HS
        return self._optimistic_mode

    @property
    def hs_color(self) -> Optional[tuple[float, float]]:
        """Return the hue and saturation color value [float, float] (0..360, 0..100)."""
        if self.coordinator.data is not None:
            if self.coordinator.data.channel_mode == "RGB":
                return (float(self.coordinator.data.hue), float(self.coordinator.data.saturation))
            return None
        return self._optimistic_hs if self._optimistic_mode == ColorMode.HS else None

    @property
    def color_temp_kelvin(self) -> Optional[int]:
        """Return the CT color value in Kelvin."""
        if self.coordinator.data is not None:
            if self.coordinator.data.channel_mode == "WHITE":
                cct_pct = self.coordinator.data.cool_white
                kelvin = MIN_COLOR_TEMP_KELVIN + (cct_pct / 100.0) * (MAX_COLOR_TEMP_KELVIN - MIN_COLOR_TEMP_KELVIN)
                return int(round(kelvin))
            return None
        return self._optimistic_cct if self._optimistic_mode == ColorMode.COLOR_TEMP else None

    @property
    def effect(self) -> Optional[str]:
        """Return the current active effect scene name."""
        if self.coordinator.data is not None and self.coordinator.data.is_scene_mode:
            preset = SCENE_PRESETS.get(self.coordinator.data.mode_id)
            if preset:
                return preset[0]
        return self._optimistic_effect

    def _get_active_brightness_percent(self, kwargs: dict[str, Any]) -> int:
        """Helper to resolve active brightness percent (1..100)."""
        if ATTR_BRIGHTNESS in kwargs:
            return max(1, min(100, int(round((kwargs[ATTR_BRIGHTNESS] / 255.0) * 100))))
        if self.coordinator.data and isinstance(getattr(self.coordinator.data, "brightness", None), int):
            if self.coordinator.data.brightness > 0:
                return max(1, min(100, self.coordinator.data.brightness))
        if isinstance(self._optimistic_brightness, int) and self._optimistic_brightness > 0:
            return max(1, min(100, int(round((self._optimistic_brightness / 255.0) * 100))))
        return 100

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on with optional attributes."""
        device = self.coordinator.device
        new_status = None
        self._optimistic_is_on = True

        if ATTR_EFFECT in kwargs:
            effect_name = kwargs[ATTR_EFFECT]
            scene_id = EFFECT_NAME_TO_ID.get(effect_name) or EFFECT_SLUG_TO_ID.get(effect_name.lower())
            if scene_id is not None:
                _LOGGER.debug("Activating scene %s (ID: 0x%02X)", effect_name, scene_id)
                self._optimistic_effect = effect_name
                
                cur_hue = None
                cur_sat = None
                cur_bri = self._get_active_brightness_percent(kwargs)
                if self.coordinator.data and self.coordinator.data.channel_mode == "RGB":
                    cur_hue = self.coordinator.data.hue
                    cur_sat = self.coordinator.data.saturation
                elif self._optimistic_hs:
                    cur_hue = int(self._optimistic_hs[0])
                    cur_sat = int(self._optimistic_hs[1])

                new_status = await device.set_scene(
                    scene_id,
                    current_hue=cur_hue,
                    current_sat=cur_sat,
                    current_bri=cur_bri,
                )
            else:
                _LOGGER.warning("Unknown effect requested: %s", effect_name)
                new_status = await device.power_on()

        elif ATTR_HS_COLOR in kwargs:
            hue, sat = kwargs[ATTR_HS_COLOR]
            bri_pct = self._get_active_brightness_percent(kwargs)
            _LOGGER.debug("Setting HS color: Hue=%.1f, Sat=%.1f, Bri=%d%%", hue, sat, bri_pct)
            self._optimistic_hs = (float(hue), float(sat))
            self._optimistic_brightness = int(round((bri_pct / 100.0) * 255))
            self._optimistic_mode = ColorMode.HS
            self._optimistic_effect = None
            new_status = await device.set_hsv(int(round(hue)) % 360, int(round(sat)), bri_pct)

        elif ATTR_RGB_COLOR in kwargs:
            r, g, b = kwargs[ATTR_RGB_COLOR]
            bri_pct = self._get_active_brightness_percent(kwargs)
            _LOGGER.debug("Setting RGB color: (%d, %d, %d)", r, g, b)
            self._optimistic_mode = ColorMode.HS
            self._optimistic_effect = None
            new_status = await device.set_rgb(r, g, b)

        elif ATTR_COLOR_TEMP_KELVIN in kwargs:
            kelvin = kwargs[ATTR_COLOR_TEMP_KELVIN]
            clamped_kelvin = max(MIN_COLOR_TEMP_KELVIN, min(MAX_COLOR_TEMP_KELVIN, kelvin))
            cct_pct = int(round(((clamped_kelvin - MIN_COLOR_TEMP_KELVIN) / (MAX_COLOR_TEMP_KELVIN - MIN_COLOR_TEMP_KELVIN)) * 100))
            bri_pct = self._get_active_brightness_percent(kwargs)
            _LOGGER.debug("Setting CCT: Kelvin=%d -> %d%%, Bri=%d%%", clamped_kelvin, cct_pct, bri_pct)
            self._optimistic_cct = clamped_kelvin
            self._optimistic_brightness = int(round((bri_pct / 100.0) * 255))
            self._optimistic_mode = ColorMode.COLOR_TEMP
            self._optimistic_effect = None
            new_status = await device.set_cct(cct_pct, bri_pct)

        elif ATTR_BRIGHTNESS in kwargs:
            bri_pct = max(1, min(100, int(round((kwargs[ATTR_BRIGHTNESS] / 255.0) * 100))))
            _LOGGER.debug("Setting brightness: %d%%", bri_pct)
            self._optimistic_brightness = kwargs[ATTR_BRIGHTNESS]
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
        self._optimistic_is_on = False
        new_status = await self.coordinator.device.power_off()
        if new_status is not None:
            self.coordinator.async_set_updated_data(new_status)
        else:
            self.async_write_ha_state()
