"""Config flow for MeshCentral."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME

from .client import MeshCentralClient
from .const import (
    CONF_LOGIN_TOKEN,
    CONF_USE_SSL,
    CONF_VERIFY_SSL,
    DEFAULT_PORT,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

# Schema when using login token (2FA accounts)
STEP_TOKEN_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
        vol.Required(CONF_LOGIN_TOKEN): str,
        vol.Optional(CONF_USE_SSL, default=False): bool,
        vol.Optional(CONF_VERIFY_SSL, default=False): bool,
    }
)

# Schema when using username + password (no 2FA)
STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Optional(CONF_USE_SSL, default=False): bool,
        vol.Optional(CONF_VERIFY_SSL, default=False): bool,
    }
)


class MeshCentralConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for MeshCentral."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """First step: choose auth method."""
        return self.async_show_menu(
            step_id="user",
            menu_options=["token", "password"],
        )

    async def async_step_token(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Login with a MeshCentral login token (works with 2FA)."""
        errors: dict[str, str] = {}

        if user_input is not None:
            token = user_input[CONF_LOGIN_TOKEN].strip()
            # Token format from MeshCentral is "username@@password"
            if "@@" in token:
                token_user, token_pass = token.split("@@", 1)
            else:
                token_user = user_input.get(CONF_USERNAME, "")
                token_pass = token

            client = MeshCentralClient(
                host=user_input[CONF_HOST],
                port=user_input[CONF_PORT],
                username=token_user,
                password=token_pass,
                use_ssl=user_input.get(CONF_USE_SSL, False),
                verify_ssl=user_input.get(CONF_VERIFY_SSL, False),
                login_token=token,
            )
            try:
                ok = await client.login()
                if not ok:
                    errors["base"] = "invalid_auth"
            except Exception:
                _LOGGER.exception("Unexpected error during token login")
                errors["base"] = "cannot_connect"
            finally:
                await client.close()

            if not errors:
                await self.async_set_unique_id(
                    f"{user_input[CONF_HOST]}:{user_input[CONF_PORT]}"
                )
                self._abort_if_unique_id_configured()
                data = dict(user_input)
                data[CONF_USERNAME] = token_user
                data[CONF_PASSWORD] = token_pass
                data[CONF_LOGIN_TOKEN] = token
                return self.async_create_entry(
                    title=f"MeshCentral ({user_input[CONF_HOST]})",
                    data=data,
                )

        return self.async_show_form(
            step_id="token",
            data_schema=STEP_TOKEN_SCHEMA,
            errors=errors,
        )

    async def async_step_password(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Login with username + password (no 2FA)."""
        errors: dict[str, str] = {}

        if user_input is not None:
            client = MeshCentralClient(
                host=user_input[CONF_HOST],
                port=user_input[CONF_PORT],
                username=user_input[CONF_USERNAME],
                password=user_input[CONF_PASSWORD],
                use_ssl=user_input.get(CONF_USE_SSL, False),
                verify_ssl=user_input.get(CONF_VERIFY_SSL, False),
            )
            try:
                ok = await client.login()
                if not ok:
                    errors["base"] = "invalid_auth"
            except Exception:
                _LOGGER.exception("Unexpected error during password login")
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
            step_id="password",
            data_schema=STEP_USER_SCHEMA,
            errors=errors,
        )
