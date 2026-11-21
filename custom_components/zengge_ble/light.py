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
    CARRIER_WAVE_EFFECT_BY_KEY,
    CARRIER_WAVE_EFFECT_LIST,
    CARRIER_WAVE_EFFECT_TEMPLATES,
    CARRIER_WAVE_MODE_TO_DEFAULT_NAME,
    CARRIER_WAVE_PRODUCT_IDS,
    CONF_LED_VERSION,
    CONF_PRODUCT_ID,
    DOMAIN,
    EFFECT_LIST,
    EFFECT_NAME_TO_ID,
    EFFECT_SLUG_TO_ID,
    MAX_COLOR_TEMP_KELVIN,
    MIN_COLOR_TEMP_KELVIN,
    PRODUCT_MODEL_NAMES,
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
    _attr_supported_features = LightEntityFeature.EFFECT
    _attr_min_color_temp_kelvin = MIN_COLOR_TEMP_KELVIN
    _attr_max_color_temp_kelvin = MAX_COLOR_TEMP_KELVIN

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
        self._optimistic_mode: ColorMode = ColorMode.HS if self._is_carrier_wave else ColorMode.COLOR_TEMP

    @property
    def _is_carrier_wave(self) -> bool:
        """Return True if this device uses the Carrier-Wave Symphony protocol (e.g. PID 0x00C5)."""
        if self.coordinator.device.is_carrier_wave:
            return True
        if self.coordinator.data and self.coordinator.data.product_id in CARRIER_WAVE_PRODUCT_IDS:
            return True
        return self._entry.data.get(CONF_PRODUCT_ID) in CARRIER_WAVE_PRODUCT_IDS

    async def async_added_to_hass(self) -> None:
        """Restore previous state on reload or boot."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state and self.coordinator.data is None:
            self._optimistic_is_on = (last_state.state == STATE_ON)
            if last_state.attributes.get(ATTR_BRIGHTNESS) is not None:
                self._optimistic_brightness = last_state.attributes[ATTR_BRIGHTNESS]
            if not self._is_carrier_wave and last_state.attributes.get(ATTR_COLOR_TEMP_KELVIN) is not None:
                self._optimistic_cct = last_state.attributes[ATTR_COLOR_TEMP_KELVIN]
                self._optimistic_mode = ColorMode.COLOR_TEMP
            elif last_state.attributes.get(ATTR_HS_COLOR) is not None:
                self._optimistic_hs = tuple(last_state.attributes[ATTR_HS_COLOR])
                self._optimistic_mode = ColorMode.HS
            if last_state.attributes.get(ATTR_EFFECT) is not None:
                self._optimistic_effect = last_state.attributes[ATTR_EFFECT]

    @property
    def supported_color_modes(self) -> set[ColorMode]:
        """Return supported color modes based on detected hardware profile."""
        if self._is_carrier_wave:
            return {ColorMode.HS}
        return {ColorMode.HS, ColorMode.COLOR_TEMP}

    @property
    def effect_list(self) -> list[str]:
        """Return supported effect list for this device model."""
        if self._is_carrier_wave:
            return CARRIER_WAVE_EFFECT_LIST
        return EFFECT_LIST

    @property
    def device_info(self) -> DeviceInfo:
        """Return device registry information."""
        address = self._entry.unique_id or self.coordinator.ble_device.address
        title = self._entry.title or self.coordinator.ble_device.name or f"Zengge Lamp {address}"
        pid = (
            self.coordinator.device.product_id
            or (self.coordinator.data.product_id if self.coordinator.data else None)
            or self._entry.data.get(CONF_PRODUCT_ID)
        )
        led_ver = (
            self.coordinator.device.led_version
            or (self.coordinator.data.led_version if self.coordinator.data else None)
            or self._entry.data.get(CONF_LED_VERSION)
        )
        default_model = (
            "HagallBjarkan Addressable String Lights"
            if self._is_carrier_wave
            else "HagallBjarkan Smart Lamp"
        )
        model = PRODUCT_MODEL_NAMES.get(pid, default_model) if pid else default_model
        info_kwargs: dict[str, Any] = {
            "identifiers": {(DOMAIN, address)},
            "name": title,
            "manufacturer": "Zengge / MagicHome",
            "model": model,
            "hw_version": "BLE 5.0",
        }
        if led_ver:
            info_kwargs["sw_version"] = f"LED v{led_ver}"
        return DeviceInfo(**info_kwargs)

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
            if (
                self._is_carrier_wave
                and self.coordinator.data.mode_id == 0x25
                and self.coordinator.device.active_carrier_effect is not None
            ):
                bri_pct = self.coordinator.device.active_carrier_brightness
            else:
                bri_pct = self.coordinator.data.brightness
            return int(round((bri_pct / 100.0) * 255))
        return self._optimistic_brightness

    @property
    def color_mode(self) -> ColorMode:
        """Return the current active color mode."""
        if self._is_carrier_wave:
            return ColorMode.HS
        if self.coordinator.data is not None:
            if self.coordinator.data.channel_mode == "WHITE":
                return ColorMode.COLOR_TEMP
            return ColorMode.HS
        return self._optimistic_mode

    @property
    def hs_color(self) -> Optional[tuple[float, float]]:
        """Return the hue and saturation color value [float, float] (0..360, 0..100)."""
        if self.coordinator.data is not None:
            if self._is_carrier_wave or self.coordinator.data.channel_mode == "RGB":
                return (float(self.coordinator.data.hue), float(self.coordinator.data.saturation))
            return None
        return self._optimistic_hs if (self._is_carrier_wave or self._optimistic_mode == ColorMode.HS) else None

    @property
    def color_temp_kelvin(self) -> Optional[int]:
        """Return the CT color value in Kelvin."""
        if self._is_carrier_wave:
            return None
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
        if self.coordinator.data is not None:
            if not self.coordinator.data.is_scene_mode:
                return None
            if self._is_carrier_wave:
                active = self.coordinator.device.active_carrier_effect
                if active and active in CARRIER_WAVE_EFFECT_TEMPLATES:
                    prefix, tail = CARRIER_WAVE_EFFECT_TEMPLATES[active]
                    eff_mode = 0x25 if prefix == "E12100" else (0x62 if prefix == "EC0300" else 0x24)
                    eff_sub = int(tail[:2], 16) if prefix != "EC0700" else 0x01
                    if self.coordinator.data.mode_id == eff_mode and self.coordinator.data.sub_mode_id == eff_sub:
                        return active
                return CARRIER_WAVE_MODE_TO_DEFAULT_NAME.get(
                    (self.coordinator.data.mode_id, self.coordinator.data.sub_mode_id)
                )
            preset = SCENE_PRESETS.get(self.coordinator.data.mode_id)
            if preset:
                return preset[0]
            return None
        return self._optimistic_effect

    def _get_active_brightness_percent(self, kwargs: dict[str, Any]) -> int:
        """Helper to resolve active brightness percent (1..100)."""
        if ATTR_BRIGHTNESS in kwargs:
            return max(1, min(100, int(round((kwargs[ATTR_BRIGHTNESS] / 255.0) * 100))))
        if (
            self._is_carrier_wave
            and self.coordinator.device.active_carrier_effect is not None
        ):
            return self.coordinator.device.active_carrier_brightness
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
            if self._is_carrier_wave:
                bri_pct = self._get_active_brightness_percent(kwargs)
                canonical = CARRIER_WAVE_EFFECT_BY_KEY.get(effect_name.strip().lower(), effect_name)
                _LOGGER.debug("Activating Carrier-Wave effect %s (bri=%d%%)", canonical, bri_pct)
                self._optimistic_effect = canonical
                self._optimistic_brightness = int(round((bri_pct / 100.0) * 255))
                self._optimistic_mode = ColorMode.HS
                new_status = await device.set_effect_by_name(effect_name, brightness=bri_pct)
            else:
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
            _LOGGER.debug("Setting RGB color: (%d, %d, %d)", r, g, b)
            self._optimistic_mode = ColorMode.HS
            self._optimistic_effect = None
            if self._is_carrier_wave and ATTR_BRIGHTNESS in kwargs:
                bri_pct = self._get_active_brightness_percent(kwargs)
                self._optimistic_brightness = kwargs[ATTR_BRIGHTNESS]
                new_status = await device.set_rgb(r, g, b, brightness=bri_pct)
            else:
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
