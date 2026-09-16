"""Credential setup, duplicate prevention and same-account reauthentication."""

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from pyequilab import (
    AccessError,
    AuthError,
    EquilabClient,
    EquilabError,
    MissingError,
    RateLimitError,
)

from .const import CONF_POLL_MINUTES, CONF_REFRESH_TOKEN, CONF_UID, DEFAULT_POLL_MINUTES, DOMAIN

SCHEMA = vol.Schema(
    {
        vol.Required("email"): selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.EMAIL)
        ),
        vol.Required("password"): selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
        ),
    }
)


class EquilabConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        return await self._credentials("user", user_input)

    async def async_step_reauth(self, entry_data):
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        return await self._credentials("reauth_confirm", user_input)

    async def _credentials(self, step, user_input):
        errors = {}
        if user_input is not None:
            client = EquilabClient(async_get_clientsession(self.hass))
            try:
                await client.async_login(user_input["email"], user_input["password"])
                if step == "reauth_confirm" and client.uid != self._get_reauth_entry().unique_id:
                    return self.async_abort(reason="wrong_account")
                await client.async_get_user()
            except AuthError:
                errors["base"] = "invalid_auth"
            except (AccessError, MissingError):
                errors["base"] = "access_denied"
            except RateLimitError:
                errors["base"] = "rate_limited"
            except EquilabError:
                errors["base"] = "cannot_connect"
            else:
                data = {CONF_UID: client.uid, CONF_REFRESH_TOKEN: client.refresh_token}
                if step == "reauth_confirm":
                    return self.async_update_reload_and_abort(self._get_reauth_entry(), data=data)
                await self.async_set_unique_id(client.uid)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=user_input["email"].strip(), data=data)
        return self.async_show_form(step_id=step, data_schema=SCHEMA, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return EquilabOptionsFlow()


class EquilabOptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(data={**self.config_entry.options, **user_input})
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_POLL_MINUTES,
                        default=self.config_entry.options.get(
                            CONF_POLL_MINUTES, DEFAULT_POLL_MINUTES
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=15, max=1440)),
                }
            ),
        )
