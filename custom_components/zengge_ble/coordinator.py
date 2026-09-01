"""DataUpdateCoordinator for Zengge HagallBjarkan BLE Light."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Optional

from bleak.backends.device import BLEDevice
from bleak.exc import BleakError

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN
from .zengge_protocol import ZenggeDeviceStatus, ZenggeLampDevice

_LOGGER = logging.getLogger(__name__)

# Polling interval for background health check / fallback status sync
POLL_INTERVAL = timedelta(seconds=60)


class ZenggeDataUpdateCoordinator(DataUpdateCoordinator[Optional[ZenggeDeviceStatus]]):
    """Coordinator to manage connection state, push notifications, and status polling."""

    def __init__(
        self,
        hass: HomeAssistant,
        ble_device: BLEDevice,
        device: ZenggeLampDevice,
    ) -> None:
        """Initialize coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{ble_device.address}",
            update_interval=POLL_INTERVAL,
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
        """Fetch latest status via query_status if connected, or maintain cached state."""
        try:
            if not self.device.is_connected:
                _LOGGER.debug("Coordinator connecting to %s for status query", self.ble_device.address)
                connected = await self.device.connect()
                if not connected:
                    # If device is currently unconnectable (e.g. lamp powered off at wall), return last known or None
                    return self.device.status

            status = await self.device.query_status()
            return status or self.device.status
        except (BleakError, asyncio.TimeoutError, ConnectionError) as err:
            _LOGGER.debug("Coordinator error querying %s: %s", self.ble_device.address, err)
            # Return last known state rather than hard-failing to preserve entity availability
            return self.device.status
