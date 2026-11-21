"""Home Assistant integration for Zengge HagallBjarkan BLE Light."""

from __future__ import annotations

import importlib
import logging
import os
import sys
from typing import Final

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth.match import BluetoothCallbackMatcher
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady

from . import const as _const_mod
from . import coordinator as _coord_mod
from . import zengge_protocol as _proto_mod
from .const import CONF_LED_VERSION, CONF_PRODUCT_ID, DOMAIN
from .coordinator import ZenggeDataUpdateCoordinator
from .zengge_protocol import ZenggeLampDevice, parse_service_data_product_info

_LOGGER = logging.getLogger(__name__)

PLATFORMS: Final[list[Platform]] = [Platform.LIGHT]

_SUBMODULE_ORDER: Final[tuple[str, ...]] = (
    "const",
    "zengge_protocol",
    "coordinator",
    "light",
    "config_flow",
)
_LOADED_MTIMES: dict[str, float] = {}


def _snapshot_submodule_mtimes() -> None:
    """Record current modification times of loaded integration submodules."""
    for sub in _SUBMODULE_ORDER:
        full_name = f"{__package__}.{sub}"
        mod = sys.modules.get(full_name)
        mod_file = getattr(mod, "__file__", None) if mod else None
        if mod_file and os.path.exists(mod_file):
            try:
                _LOADED_MTIMES[full_name] = os.path.getmtime(mod_file)
            except OSError:
                pass


_snapshot_submodule_mtimes()


def _reload_submodules_if_changed() -> bool:
    """Reload integration submodules in topological order if any file on disk changed."""
    changed = False
    for sub in _SUBMODULE_ORDER:
        full_name = f"{__package__}.{sub}"
        mod = sys.modules.get(full_name)
        mod_file = getattr(mod, "__file__", None) if mod else None
        if mod_file and os.path.exists(mod_file):
            try:
                mtime = os.path.getmtime(mod_file)
            except OSError:
                continue
            if mtime > _LOADED_MTIMES.get(full_name, 0.0):
                changed = True
                break

    if not changed:
        return False

    importlib.invalidate_caches()
    for sub in _SUBMODULE_ORDER:
        full_name = f"{__package__}.{sub}"
        mod = sys.modules.get(full_name)
        if mod is not None:
            try:
                importlib.reload(mod)
            except Exception as err:
                _LOGGER.warning("Hot-reload failed for %s: %s", full_name, err)
    _snapshot_submodule_mtimes()
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Zengge BLE Light from a config entry."""
    global CONF_LED_VERSION, CONF_PRODUCT_ID, DOMAIN
    global ZenggeDataUpdateCoordinator, ZenggeLampDevice, parse_service_data_product_info

    if await hass.async_add_executor_job(_reload_submodules_if_changed):
        const_mod = sys.modules.get(f"{__package__}.const", _const_mod)
        proto_mod = sys.modules.get(f"{__package__}.zengge_protocol", _proto_mod)
        coord_mod = sys.modules.get(f"{__package__}.coordinator", _coord_mod)
        CONF_LED_VERSION = const_mod.CONF_LED_VERSION
        CONF_PRODUCT_ID = const_mod.CONF_PRODUCT_ID
        DOMAIN = const_mod.DOMAIN
        ZenggeDataUpdateCoordinator = coord_mod.ZenggeDataUpdateCoordinator
        ZenggeLampDevice = proto_mod.ZenggeLampDevice
        parse_service_data_product_info = proto_mod.parse_service_data_product_info
        _LOGGER.info("Hot-reloaded modified zengge_ble submodules without restarting Home Assistant")

    address: str = entry.data[CONF_ADDRESS]

    ble_device = bluetooth.async_ble_device_from_address(hass, address, connectable=True)
    if not ble_device:
        _LOGGER.debug("BLE device %s not yet discovered by Bluetooth stack; will retry", address)
        raise ConfigEntryNotReady(f"Could not find Bluetooth device with address {address}")

    product_id: int | None = entry.data.get(CONF_PRODUCT_ID)
    led_version: int | None = entry.data.get(CONF_LED_VERSION)

    last_info_fn = getattr(bluetooth, "async_last_service_info", None)
    if callable(last_info_fn):
        service_info = last_info_fn(hass, address, connectable=True)
        if service_info is not None:
            adv_pid, _fw, adv_led = parse_service_data_product_info(
                getattr(service_info, "service_data", None)
            )
            if product_id is None and adv_pid is not None:
                product_id = adv_pid
            if led_version is None and adv_led is not None:
                led_version = adv_led

    device = ZenggeLampDevice(
        ble_device=ble_device,
        address=address,
        product_id=product_id,
        led_version=led_version,
    )
    coordinator = ZenggeDataUpdateCoordinator(hass, ble_device=ble_device, device=device)

    @callback
    def _maybe_persist_product_info(pid: int | None, led: int | None) -> None:
        if pid is None or pid <= 0:
            return
        if entry.data.get(CONF_PRODUCT_ID) == pid and (led is None or entry.data.get(CONF_LED_VERSION) == led):
            return
        updated_data = dict(entry.data)
        updated_data[CONF_PRODUCT_ID] = pid
        if led is not None and led > 0:
            updated_data[CONF_LED_VERSION] = led
        hass.config_entries.async_update_entry(entry, data=updated_data)

    # Register dynamic Bluetooth callback to track proxy roaming / advertisement updates
    @callback
    def _async_bluetooth_callback(
        service_info: bluetooth.BluetoothServiceInfoBleak,
        change: bluetooth.BluetoothChange,
    ) -> None:
        """Update BLEDevice object and hardware metadata when new advertisement arrives."""
        adv_pid, _fw, adv_led = parse_service_data_product_info(
            getattr(service_info, "service_data", None)
        )
        if adv_pid is not None:
            device.set_product_info(adv_pid, adv_led)
            _maybe_persist_product_info(adv_pid, adv_led)
        coordinator.update_ble_device(service_info.device)
        if coordinator.data is None:
            hass.async_create_task(coordinator.async_request_refresh())

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

    if device.product_id:
        _maybe_persist_product_info(device.product_id, device.led_version)

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
