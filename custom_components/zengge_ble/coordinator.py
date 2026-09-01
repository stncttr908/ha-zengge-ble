"""DataUpdateCoordinator for Zengge HagallBjarkan BLE Light."""

from __future__ import annotations

import logging
from typing import Optional

from bleak.backends.device import BLEDevice

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN
from .zengge_protocol import ZenggeDeviceStatus, ZenggeLampDevice

_LOGGER = logging.getLogger(__name__)


class ZenggeDataUpdateCoordinator(DataUpdateCoordinator[Optional[ZenggeDeviceStatus]]):
    """Coordinator to manage connection state and push notifications."""

    def __init__(
        self,
        hass: HomeAssistant,
        ble_device: BLEDevice,
        device: ZenggeLampDevice,
    ) -> None:
        """Initialize coordinator without periodic polling (pure push updates)."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{ble_device.address}",
            update_interval=None,  # Pure push architecture: state pushes via 0xFF02 notifications
        )
        self.ble_device = ble_device
        self.device = device
        self._unregister_callback: Optional[callable] = None

    @callback
    def async_start(self) -> None:
        """Attach listeners for push telemetry updates."""
        self._unregister_callback = self.device.register_status_callback(self._handle_status_update)

    @callback
    def async_stop(self) -> None:
        """Detach listeners."""
        if self._unregister_callback:
            self._unregister_callback()
            self._unregister_callback = None

    @callback
    def _handle_status_update(self, status: ZenggeDeviceStatus) -> None:
        """Handle incoming telemetry push from 0xFF02 notifications."""
        _LOGGER.debug("Received push telemetry for %s: power=%s, mode=%s", self.ble_device.address, status.power, status.mode_name)
        self.async_set_updated_data(status)

    @callback
    def update_ble_device(self, ble_device: BLEDevice) -> None:
        """Update BLEDevice reference when advertisement source or proxy changes."""
        self.ble_device = ble_device
        self.device.set_ble_device(ble_device)

    async def _async_update_data(self) -> Optional[ZenggeDeviceStatus]:
        """Establish connection and query initial status on startup."""
        if not self.device.is_connected:
            try:
                connected = await self.device.connect()
                if connected and not self.device.status:
                    await self.device.query_status()
            except Exception as err:
                _LOGGER.debug("Initial startup query for %s: %s", self.ble_device.address, err)
        return self.device.status
