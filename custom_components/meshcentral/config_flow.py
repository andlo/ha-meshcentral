"""Config flow for MeshCentral."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.core import callback

from .client import MeshCentralClient
from .const import (
    CONF_HW_SCAN_INTERVAL,
    CONF_LOGIN_KEY,
    CONF_MAIN_SCAN_INTERVAL,
    CONF_USE_SSL,
    CONF_VERIFY_SSL,
    DEFAULT_HW_SCAN_INTERVAL,
    DEFAULT_MAIN_SCAN_INTERVAL,
    DEFAULT_PORT,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Optional(CONF_LOGIN_KEY, default=""): str,
        vol.Optional(CONF_USE_SSL, default=False): bool,
        vol.Optional(CONF_VERIFY_SSL, default=False): bool,
    }
)


class MeshCentralConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for MeshCentral."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> MeshCentralOptionsFlow:
        return MeshCentralOptionsFlow(config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            login_key = user_input.get(CONF_LOGIN_KEY) or None
            client = MeshCentralClient(
                host=user_input[CONF_HOST],
                port=user_input[CONF_PORT],
                username=user_input[CONF_USERNAME],
                password=user_input[CONF_PASSWORD],
                use_ssl=user_input.get(CONF_USE_SSL, False),
                verify_ssl=user_input.get(CONF_VERIFY_SSL, False),
                login_key=login_key,
            )
            try:
                ok = await client.login()
                if not ok:
                    errors["base"] = "invalid_auth"
            except Exception:
                _LOGGER.exception("Unexpected error during login")
                errors["base"] = "cannot_connect"
            finally:
                await client.close()

            if not errors:
                await self.async_set_unique_id(
                    f"{user_input[CONF_HOST]}:{user_input[CONF_PORT]}"
                )
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"MeshCentral ({user_input[CONF_HOST]})",
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_SCHEMA,
            errors=errors,
        )


class MeshCentralOptionsFlow(OptionsFlow):
    """Options flow: let the user tune the poll intervals.

    self.config_entry is provided automatically by the base OptionsFlow
    class (HA 2024.12+) — no need to store it ourselves.
    """

    def __init__(self, config_entry) -> None:
        pass

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        current = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_MAIN_SCAN_INTERVAL,
                    default=current.get(CONF_MAIN_SCAN_INTERVAL, DEFAULT_MAIN_SCAN_INTERVAL),
                ): vol.All(int, vol.Range(min=1, max=60)),
                vol.Optional(
                    CONF_HW_SCAN_INTERVAL,
                    default=current.get(CONF_HW_SCAN_INTERVAL, DEFAULT_HW_SCAN_INTERVAL),
                ): vol.All(int, vol.Range(min=1, max=60)),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
