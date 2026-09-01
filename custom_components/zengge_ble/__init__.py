"""Home Assistant integration for Zengge HagallBjarkan BLE Light."""

from __future__ import annotations

import importlib
import logging
import sys
from typing import Final

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth.match import BluetoothCallbackMatcher
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady

# Dynamic submodule refresh on reload
for mod_name in list(sys.modules.keys()):
    if mod_name.startswith("custom_components.zengge_ble.") and not mod_name.endswith(".config_flow"):
        try:
            importlib.reload(sys.modules[mod_name])
        except Exception:
            pass

from .const import DOMAIN
from .coordinator import ZenggeDataUpdateCoordinator
from .zengge_protocol import ZenggeLampDevice

_LOGGER = logging.getLogger(__name__)

PLATFORMS: Final[list[Platform]] = [Platform.LIGHT]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Zengge BLE Light from a config entry."""
    address: str = entry.data[CONF_ADDRESS]

    ble_device = bluetooth.async_ble_device_from_address(hass, address, connectable=True)
    if not ble_device:
        _LOGGER.debug("BLE device %s not yet discovered by Bluetooth stack; will retry", address)
        raise ConfigEntryNotReady(f"Could not find Bluetooth device with address {address}")

    device = ZenggeLampDevice(ble_device=ble_device, address=address)
    coordinator = ZenggeDataUpdateCoordinator(hass, ble_device=ble_device, device=device)

    # Register dynamic Bluetooth callback to track proxy roaming / advertisement updates
    @callback
    def _async_bluetooth_callback(
        service_info: bluetooth.BluetoothServiceInfoBleak,
        change: bluetooth.BluetoothChange,
    ) -> None:
        """Update BLEDevice object when new advertisement arrives."""
        coordinator.update_ble_device(service_info.device)

    entry.async_on_unload(
        bluetooth.async_register_callback(
            hass,
            _async_bluetooth_callback,
            BluetoothCallbackMatcher(address=address, connectable=True),
            bluetooth.BluetoothScanningMode.PASSIVE,
        )
    )

    coordinator.async_start()

    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:
        _LOGGER.debug("Initial status query for %s failed (%s); continuing setup in cached state", address, err)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator: ZenggeDataUpdateCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        coordinator.async_stop()
        await coordinator.device.disconnect()

        if not hass.data[DOMAIN]:
            hass.data.pop(DOMAIN, None)

    return unload_ok
