"""Config flow for Zengge HagallBjarkan BLE Light integration."""

from __future__ import annotations

import logging
import re
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN, SERVICE_UUID

_LOGGER = logging.getLogger(__name__)

MAC_PATTERN = re.compile(r"^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$")


def format_mac(address: str) -> str:
    """Format and normalize MAC address to uppercase colon-separated string."""
    clean = re.sub(r"[^0-9A-Fa-f]", "", address).upper()
    if len(clean) == 12:
        return ":".join(clean[i : i + 2] for i in range(0, 12, 2))
    return address.upper()


class ZenggeBLEConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Zengge BLE Light."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize config flow."""
        super().__init__()
        self.context = getattr(self, "context", {}) or {}
        self._discovery_info: BluetoothServiceInfoBleak | None = None
        self._discovered_devices: dict[str, BluetoothServiceInfoBleak] = {}

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> FlowResult:
        """Handle bluetooth discovery initiated by Home Assistant."""
        _LOGGER.debug("Discovered Zengge BLE device via Bluetooth: %s (%s)", discovery_info.name, discovery_info.address)
        formatted_address = format_mac(discovery_info.address)
        await self.async_set_unique_id(formatted_address)
        self._abort_if_unique_id_configured()

        self._discovery_info = discovery_info
        title = discovery_info.name or f"Zengge Lamp {formatted_address}"
        self.context["title_placeholders"] = {"name": title}
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Confirm discovery of a bluetooth device."""
        assert self._discovery_info is not None

        if user_input is not None:
            formatted_address = format_mac(self._discovery_info.address)
            title = self._discovery_info.name or f"Zengge Lamp {formatted_address}"
            return self.async_create_entry(
                title=title,
                data={
                    CONF_ADDRESS: formatted_address,
                    CONF_NAME: title,
                },
            )

        name = self._discovery_info.name or self._discovery_info.address
        return self.async_show_form(
            step_id="bluetooth_confirm",
            description_placeholders={"name": name},
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle user-initiated setup step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            address = user_input.get(CONF_ADDRESS)
            if address == "manual":
                return await self.async_step_manual()

            if address:
                formatted_address = format_mac(address)
                await self.async_set_unique_id(formatted_address, raise_on_progress=False)
                self._abort_if_unique_id_configured()

                info = self._discovered_devices.get(formatted_address) or self._discovered_devices.get(address)
                title = (info.name if info else None) or f"Zengge Lamp {formatted_address}"
                return self.async_create_entry(
                    title=title,
                    data={
                        CONF_ADDRESS: formatted_address,
                        CONF_NAME: title,
                    },
                )

        current_addresses = self._async_current_ids()
        self._discovered_devices = {}
        device_choices: dict[str, str] = {}

        for discovery_info in async_discovered_service_info(self.hass, connectable=True):
            formatted_addr = format_mac(discovery_info.address)
            if formatted_addr in current_addresses:
                continue

            name = discovery_info.name or ""
            service_uuids = [str(u).lower() for u in discovery_info.service_uuids]

            # Match standard Zengge service UUID 0xFFFF or name prefixes
            is_match = False
            if SERVICE_UUID.lower() in service_uuids or "ffff" in "".join(service_uuids):
                is_match = True
            elif name.upper().startswith("IOTBT") or "ZENGGE" in name.upper() or "MAGIC" in name.upper():
                is_match = True

            if is_match:
                self._discovered_devices[formatted_addr] = discovery_info
                display_name = f"{name or 'Zengge Lamp'} ({formatted_addr})"
                device_choices[formatted_addr] = display_name

        if not device_choices:
            return await self.async_step_manual()

        device_choices["manual"] = "Manually enter Bluetooth MAC address"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ADDRESS): vol.In(device_choices),
                }
            ),
            errors=errors,
        )

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle manual Bluetooth MAC entry."""
        errors: dict[str, str] = {}

        if user_input is not None:
            raw_address = user_input.get(CONF_ADDRESS, "").strip()
            formatted_address = format_mac(raw_address)

            if not MAC_PATTERN.match(formatted_address):
                errors[CONF_ADDRESS] = "invalid_mac"
            else:
                await self.async_set_unique_id(formatted_address, raise_on_progress=False)
                self._abort_if_unique_id_configured()

                title = user_input.get(CONF_NAME) or f"Zengge Lamp {formatted_address}"
                return self.async_create_entry(
                    title=title,
                    data={
                        CONF_ADDRESS: formatted_address,
                        CONF_NAME: title,
                    },
                )

        return self.async_show_form(
            step_id="manual",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ADDRESS): str,
                    vol.Optional(CONF_NAME): str,
                }
            ),
            errors=errors,
        )
