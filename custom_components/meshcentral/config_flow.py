"""Config flow for MeshCentral."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .client import MeshCentralClient
from .const import (
    CONF_HW_SCAN_INTERVAL,
    CONF_LOGIN_KEY,
    CONF_MAIN_SCAN_INTERVAL,
    CONF_SELECTED_MESH_IDS,
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
    """Options flow: poll intervals and device group filtering (#47).

    self.config_entry is provided automatically by the base OptionsFlow
    class (HA 2024.12+) — no need to store it ourselves.
    """

    def __init__(self, config_entry) -> None:
        pass

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Landing menu: general poll settings, or device group filtering."""
        return self.async_show_menu(
            step_id="init",
            menu_options=["general", "groups"],
        )

    async def async_step_general(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            # Merge into existing options rather than replacing them — this
            # step only ever edits the two scan-interval keys, so a bare
            # async_create_entry(data=user_input) here would silently wipe
            # any CONF_SELECTED_MESH_IDS set via the "groups" step.
            return self.async_create_entry(
                data={**self.config_entry.options, **user_input}
            )

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
        return self.async_show_form(step_id="general", data_schema=schema)

    async def async_step_groups(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Select which MeshCentral device groups to import (#47).

        Selection is stored by mesh ID, not name, so renaming a group on
        the MeshCentral side doesn't silently drop it from the filter. An
        empty selection means "all groups" — the pre-#47 default, so
        existing installs keep their current behavior after upgrading.
        """
        if user_input is not None:
            return self.async_create_entry(
                data={
                    **self.config_entry.options,
                    CONF_SELECTED_MESH_IDS: user_input.get(
                        CONF_SELECTED_MESH_IDS, []
                    ),
                }
            )

        entry_data = self.config_entry.data
        client = MeshCentralClient(
            host=entry_data[CONF_HOST],
            port=entry_data[CONF_PORT],
            username=entry_data[CONF_USERNAME],
            password=entry_data[CONF_PASSWORD],
            use_ssl=entry_data.get(CONF_USE_SSL, False),
            verify_ssl=entry_data.get(CONF_VERIFY_SSL, False),
            login_key=entry_data.get(CONF_LOGIN_KEY) or None,
        )
        errors: dict[str, str] = {}
        groups: list[dict] = []
        try:
            if await client.login():
                groups = await client.get_device_groups()
                if not groups:
                    errors["base"] = "no_groups"
            else:
                errors["base"] = "cannot_connect"
        except Exception:
            _LOGGER.exception("Failed to fetch device groups for options flow")
            errors["base"] = "cannot_connect"
        finally:
            await client.close()

        if errors:
            return self.async_show_form(step_id="groups", errors=errors)

        group_options = [
            SelectOptionDict(value=group["_id"], label=group.get("name") or group["_id"])
            for group in groups
            if "_id" in group
        ]
        current_selection = [
            mesh_id
            for mesh_id in self.config_entry.options.get(CONF_SELECTED_MESH_IDS, [])
            if mesh_id in {g["value"] for g in group_options}
        ]

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_SELECTED_MESH_IDS,
                    default=current_selection,
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=group_options,
                        multiple=True,
                        mode=SelectSelectorMode.LIST,
                    )
                ),
            }
        )
        return self.async_show_form(step_id="groups", data_schema=schema)
