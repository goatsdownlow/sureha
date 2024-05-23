"""The surepetcare integration."""
from __future__ import annotations

from datetime import timedelta
import logging
from random import choice
from typing import Any
from datetime import datetime
from importlib.metadata import version
from logging import Logger
from math import ceil
from typing import Any
from uuid import uuid1
import aiohttp

import async_timeout
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_TOKEN, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from sureha import Sureha
from sureha.entities import SurepyEntity
from sureha.enums import EntityType, Location, LockState
from sureha.exceptions import SurePetcareAuthenticationError, SurePetcareError
import voluptuous as vol


from rich.console import Console

from sureha.client import SureAPIClient, find_token, token_seems_valid
from sureha.const import (
    API_TIMEOUT,
    ATTRIBUTES_RESOURCE as ATTR_RESOURCE,
    BASE_RESOURCE,
    HOUSEHOLD_TIMELINE_RESOURCE,
    MESTART_RESOURCE,
    NOTIFICATION_RESOURCE,
    TIMELINE_RESOURCE,
)

from sureha.entities.devices import Feeder, Felaqua, Flap, Hub, SurepyDevice
from sureha.entities.pet import Pet
from sureha.enums import EntityType



# pylint: disable=import-error
from .const import (
    ATTR_FLAP_ID,
    ATTR_LOCK_STATE,
    ATTR_PET_ID,
    ATTR_DEVICE_ID,
    ATTR_TAG_ID,
    ATTR_WHERE,
    DOMAIN,
    SERVICE_PET_LOCATION,
    SERVICE_ADD_TO_FEEDER,
    SERVICE_REMOVE_FROM_FEEDER,
    SERVICE_SET_LOCK_STATE,
    SPC,
    SURE_API_TIMEOUT,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["binary_sensor", "device_tracker", "sensor"]
SCAN_INTERVAL = timedelta(minutes=3)

__version__ = version(__name__)

# TOKEN_ENV = "SUREPY_TOKEN"  # nosec
# TOKEN_FILE = Path("~/.surepy.token").expanduser()

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            vol.All(
                {
                    vol.Required(CONF_USERNAME): cv.string,
                    vol.Required(CONF_PASSWORD): cv.string,
                }
            )
        )
    },
    extra=vol.ALLOW_EXTRA,
)

CATS = [
    "/ᐠ｡▿｡ᐟ\\*ᵖᵘʳʳ",
    "/ᐠ_ꞈ_ᐟ\\ɴʏᴀ~",
    "/ᐠ ._. ᐟ\\ﾉ",
    "/ᐠ. ｡.ᐟ\\ᵐᵉᵒʷˎˊ",
    "ᶠᵉᵉᵈ ᵐᵉ /ᐠ-ⱉ-ᐟ\\ﾉ",
    "(≗ᆽ ≗)ﾉ",
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up."""

    hass.data.setdefault(DOMAIN, {})

    try:
        surepy = Surepy(
            entry.data[CONF_USERNAME],
            entry.data[CONF_PASSWORD],
            auth_token=entry.data[CONF_TOKEN] if CONF_TOKEN in entry.data else None,
            api_timeout=SURE_API_TIMEOUT,
            session=async_get_clientsession(hass),
        )
    except SurePetcareAuthenticationError:
        _LOGGER.error(
            "🐾 \x1b[38;2;255;26;102m·\x1b[0m unable to auth. to surepetcare.io: wrong credentials"
        )
        return False
    except SurePetcareError as error:
        _LOGGER.error(
            "🐾 \x1b[38;2;255;26;102m·\x1b[0m unable to connect to surepetcare.io: %s",
            error,
        )
        return False

    spc = SurePetcareAPI(hass, entry, surepy)

    async def async_update_data():

        try:
            # asyncio.TimeoutError and aiohttp.ClientError already handled

            async with async_timeout.timeout(20):
                return await spc.surepy.get_entities(refresh=True)

        except SurePetcareAuthenticationError as err:
            raise ConfigEntryAuthFailed from err
        except SurePetcareError as err:
            raise UpdateFailed(f"Error communicating with API: {err}") from err

    spc.coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="sureha_sensors",
        update_method=async_update_data,
        update_interval=timedelta(seconds=150),
    )

    await spc.coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][SPC] = spc

    return await spc.async_setup()


class SurePetcareAPI:
    """Define a generic Sure Petcare object."""

    def __init__(
        self, hass: HomeAssistant, config_entry: ConfigEntry, surepy: Surepy
    ) -> None:
        """Initialize the Sure Petcare object."""

        self.coordinator: DataUpdateCoordinator

        self.hass = hass
        self.config_entry = config_entry
        self.surepy = surepy

        self.states: dict[int, Any] = {}

    async def set_pet_location(self, pet_id: int, location: Location) -> None:
        """Update the lock state of a flap."""

        await self.surepy.sac.set_pet_location(pet_id, location)

    async def add_to_feeder(self, device_id: int, tag_id: int) -> None:
        """Add pet to feeder."""

        await self.surepy.sac._add_tag_to_device(device_id, tag_id)
    
    async def trial_add_tag_to_device(self, device_id: int, tag_id: int) -> None:
        """TRIAL Add the specified tag ID to the specified device ID"""
        
        
        resource = "https://app.api.surehub.io/api/device/" + str(device_id) + "/tag/"  + str(tag_id)
        data = {}
        await self.surepy.sac.call(method="PUT", resource=resource, data=data)
        
    async def remove_from_feeder(self, device_id: int, tag_id: int) -> None:
        """Remove pet from to feeder."""
        
        await self.surepy.sac._remove_tag_from_device(device_id, tag_id)

    async def set_lock_state(self, flap_id: int, state: str) -> None:
        """Update the lock state of a flap."""

        # https://github.com/PyCQA/pylint/issues/2062
        # pylint: disable=no-member
        lock_states = {
            LockState.UNLOCKED.name.lower(): self.surepy.sac.unlock,
            LockState.LOCKED_IN.name.lower(): self.surepy.sac.lock_in,
            LockState.LOCKED_OUT.name.lower(): self.surepy.sac.lock_out,
            LockState.LOCKED_ALL.name.lower(): self.surepy.sac.lock,
        }

        # elegant functions dict to choose the right function | idea by @janiversen
        await lock_states[state.lower()](flap_id)

    async def async_setup(self) -> bool:
        """Set up the Sure Petcare integration."""

        _LOGGER.info("")
        _LOGGER.info(
            "%s %s", " \x1b[38;2;255;26;102m·\x1b[0m" * 24, choice(CATS)  # nosec
        )
        _LOGGER.info("  🐾   meeowww..! to the SureHA integration!")
        _LOGGER.info("  🐾     code & issues: https://github.com/benleb/sureha")
        _LOGGER.info(" \x1b[38;2;255;26;102m·\x1b[0m" * 30)
        _LOGGER.info("")

        self.hass.async_add_job(
            self.hass.config_entries.async_forward_entry_setup(  # type: ignore
                self.config_entry, "binary_sensor"
            )
        )

        self.hass.async_add_job(
            self.hass.config_entries.async_forward_entry_setup(  # type: ignore
                self.config_entry, "sensor"
            )
        )

        self.hass.async_add_job(
            self.hass.config_entries.async_forward_entry_setup(  # type: ignore
                self.config_entry, "device_tracker"
            )
        )

        surepy_entities: list[SurepyEntity] = self.coordinator.data.values()

        pet_ids = [
            entity.id for entity in surepy_entities if entity.type == EntityType.PET
        ]

        pet_location_service_schema = vol.Schema(
            {
                vol.Required(ATTR_PET_ID): vol.Any(cv.positive_int, vol.In(pet_ids)),
                vol.Required(ATTR_WHERE): vol.Any(
                    cv.string,
                    vol.In(
                        [
                            # https://github.com/PyCQA/pylint/issues/2062
                            # pylint: disable=no-member
                            Location.INSIDE.name.title(),
                            Location.OUTSIDE.name.title(),
                        ]
                    ),
                ),
            }
        )
        device_pet_schema = vol.Schema(
            {
                vol.Required(ATTR_TAG_ID): vol.Any(cv.positive_int, cv.positive_int),
                vol.Required(ATTR_DEVICE_ID): vol.Any(cv.positive_int, cv.positive_int)
            }
        )

        async def handle_set_pet_location(call: Any) -> None:
            """Call when setting the lock state."""

            try:

                if (pet_id := int(call.data.get(ATTR_PET_ID))) and (
                    where := str(call.data.get(ATTR_WHERE))
                ):

                    await self.set_pet_location(pet_id, Location[where.upper()])
                    await self.coordinator.async_request_refresh()

            except ValueError as error:
                _LOGGER.error(
                    "🐾 \x1b[38;2;255;26;102m·\x1b[0m arguments of wrong type: %s", error
                )

        self.hass.services.async_register(
            DOMAIN,
            SERVICE_PET_LOCATION,
            handle_set_pet_location,
            schema=pet_location_service_schema,
        )

        async def handle_add_to_feeder(call: Any) -> None:
            """Call when adding to feeder."""

            try:

                if (tag_id := int(call.data.get(ATTR_TAG_ID))) and (
                    device_id := int(call.data.get(ATTR_DEVICE_ID))
                ):

                    # await self.add_to_feeder(device_id, tag_id)
                    await self.trial_add_tag_to_device(device_id, tag_id)
                    await self.coordinator.async_request_refresh()

            except ValueError as error:
                _LOGGER.error(
                    "🐾 \x1b[38;2;255;26;102m·\x1b[0m arguments of wrong type: %s", error
                )
        
        self.hass.services.async_register(
            DOMAIN,
            SERVICE_ADD_TO_FEEDER,
            handle_add_to_feeder,
            schema=device_pet_schema,
        )

        async def handle_remove_from_feeder(call: Any) -> None:
            """Call when removing from feeder."""

            try:

                if (tag_id := int(call.data.get(ATTR_TAG_ID))) and (
                    device_id := int(call.data.get(ATTR_DEVICE_ID))
                ):

                    await self.remove_from_feeder(device_id, tag_id)
                    await self.coordinator.async_request_refresh()

            except ValueError as error:
                _LOGGER.error(
                    "🐾 \x1b[38;2;255;26;102m·\x1b[0m arguments of wrong type: %s", error
                )

        self.hass.services.async_register(
            DOMAIN,
            SERVICE_REMOVE_FROM_FEEDER,
            handle_remove_from_feeder,
            schema=device_pet_schema,
        )

        async def handle_set_lock_state(call: Any) -> None:
            """Call when setting the lock state."""

            flap_id = call.data.get(ATTR_FLAP_ID)
            lock_state = call.data.get(ATTR_LOCK_STATE)

            await self.set_lock_state(flap_id, lock_state)
            await self.coordinator.async_request_refresh()

        flap_ids = [
            entity.id
            for entity in surepy_entities
            if entity.type in [EntityType.CAT_FLAP, EntityType.PET_FLAP]
        ]

        lock_state_service_schema = vol.Schema(
            {
                vol.Required(ATTR_FLAP_ID): vol.All(cv.positive_int, vol.In(flap_ids)),
                vol.Required(ATTR_LOCK_STATE): vol.All(
                    cv.string,
                    vol.Lower,
                    vol.In(
                        [
                            # https://github.com/PyCQA/pylint/issues/2062
                            # pylint: disable=no-member
                            LockState.UNLOCKED.name.lower(),
                            LockState.LOCKED_IN.name.lower(),
                            LockState.LOCKED_OUT.name.lower(),
                            LockState.LOCKED_ALL.name.lower(),
                        ]
                    ),
                ),
            }
        )

        self.hass.services.async_register(
            DOMAIN,
            SERVICE_SET_LOCK_STATE,
            handle_set_lock_state,
            schema=lock_state_service_schema,
        )

        return True

# FROM surepy _init_.py

def natural_time(duration: int) -> str:
    """Transforms a number of seconds to a more human-friendly string.

    Args:
        duration (int): duration in seconds

    Returns:
        str: human-friendly duration string
    """

    duration_h, duration_min = divmod(duration, int(60 * 60))
    duration_min, duration_sec = divmod(duration_min, int(60))

    # append suitable unit
    if duration >= 60 * 60 * 24:
        duration_d, duration_h = divmod(duration_h, int(24))
        natural = f"{int(duration_d)}d {int(duration_h)}h {int(duration_min)}m"

    elif duration >= 60 * 60:
        if duration_min < 2 or duration_min > 58:
            natural = f"{int(duration_h)}h"
        else:
            natural = f"{int(duration_h)}h {int(duration_min)}m"

    elif duration > 60:
        natural = f"{int(duration_min)}min"

    else:
        natural = f"{int(duration_sec)}sec"

    return natural


class Surepy:
    """Communication with the Sure Petcare API."""

    def __init__(
        self,
        email: str | None = None,
        password: str | None = None,
        auth_token: str | None = None,
        api_timeout: int = API_TIMEOUT,
        session: aiohttp.ClientSession | None = None,
    ) -> None:
        """Initialize the connection to the Sure Petcare API."""

        # random device id
        self._device_id: str = str(uuid1())

        self._session = session

        self.sac = SureAPIClient(
            email=email,
            password=password,
            auth_token=auth_token,
            api_timeout=api_timeout,
            session=self._session,
            surepy_version=__version__,
        )

        # api token management
        self._auth_token: str | None = None
        if auth_token and token_seems_valid(auth_token):
            self._auth_token = auth_token
        else:  # if token := find_token():
            self._auth_token = find_token()

        self.entities: dict[int, SurepyEntity] = {}
        self._pets: dict[int, Any] = {}
        self._flaps: dict[int, Any] = {}
        self._feeders: dict[int, Any] = {}
        self._hubs: dict[int, Any] = {}

        self._breeds: dict[int, dict[int, Any]] = {}
        self._species_breeds: dict[int, dict[int, Any]] = {}
        self._conditions: dict[int, Any] = {}

        # storage for received api data
        self._resource: dict[str, Any] = {}
        # storage for etags
        self._etags: dict[str, str] = {}

        logger.debug("initialization completed | vars(): %s", vars())

    @property
    def auth_token(self) -> str | None:
        """Authentication token for device"""
        return self._auth_token

    async def pets_details(self) -> list[dict[str, Any]] | None:
        """Fetch pet information."""
        return await self.sac.get_pets()

    async def latest_actions(self, household_id: int) -> dict[int, dict[str, Any]] | None:
        """
        Args:
            household_id (int): ID associated with household
            pet_id (int): ID associated with pet

        Returns:
            Get the latest action using pet_id and household_id
            from raw data and output as a dictionary
        """
        return await self.get_actions(household_id=household_id)

    async def all_actions(self, household_id: int) -> dict[int, dict[str, Any]] | None:
        """Args:
        - household_id (int): id associated with household
        - pet_id (int): id associated with pet
        """
        return await self.get_actions(household_id=household_id)

    async def get_actions(self, household_id: int) -> dict[int, dict[str, Any]] | None:
        resource = f"{BASE_RESOURCE}/report/household/{household_id}"

        latest_actions: dict[int, dict[str, Any]] = {}

        pet_device_pairs: dict[str, Any] = (
            await self.sac.call(method="GET", resource=resource) or {}
        )

        if "data" not in pet_device_pairs:
            return latest_actions

        data: list[dict[str, Any]] = pet_device_pairs["data"]

        for pair in data:

            pet_id = int(pair["pet_id"])
            device_id = int(pair["device_id"])
            device: SurepyDevice = self.entities[device_id]  # type: ignore

            latest_actions[pet_id] = {}
            latest_actions[pet_id] = self.entities[device_id]._data

            # movement
            if (
                device.type in [EntityType.CAT_FLAP, EntityType.PET_FLAP]
                and pair["movement"]["datapoints"]
            ):
                latest_datapoint = pair["movement"]["datapoints"].pop()
                # latest_actions[pet_id]["move"] = latest_datapoint
                latest_actions[pet_id] = self.entities[device_id]._data["move"] = latest_datapoint

            # feeding
            elif (
                device.type in [EntityType.FEEDER, EntityType.FEEDER_LITE]
                and pair["feeding"]["datapoints"]
            ):
                latest_datapoint = pair["feeding"]["datapoints"].pop()
                # latest_actions[pet_id]["lunch"] = latest_datapoint
                latest_actions[pet_id] = self.entities[device_id]._data["lunch"] = latest_datapoint

            # drinking
            elif device.type == EntityType.FELAQUA and pair["drinking"]["datapoints"]:
                latest_datapoint = pair["drinking"]["datapoints"].pop()
                # latest_actions[pet_id]["drink"] = latest_datapoint
                latest_actions[pet_id] = self.entities[device_id]._data["drink"] = latest_datapoint

        return latest_actions

    async def get_latest_anonymous_drinks(self, household_id: int) -> dict[str, Any] | None:

        latest_drink: dict[str, float | str | datetime] = {}

        household_timeline = await self.get_household_timeline(household_id, entries=50)

        felaqua_related_entries: list[dict[str, Any]] = list(
            filter(
                lambda x: x["type"] in [29, 30, 34],  # type: ignore
                household_timeline,  # type: ignore
            )
        )

        if felaqua_related_entries:
            try:
                device_id = felaqua_related_entries[0]["weights"][0]["device_id"]
                latest_entry_frame = felaqua_related_entries[0]["weights"][0]["frames"][0]
                remaining = latest_entry_frame["current_weight"]
                change = latest_entry_frame["change"]
                updated_at = latest_entry_frame["updated_at"]
                latest_drink = {"remaining": remaining, "change": change, "date": updated_at}

                self.entities[device_id]._data["latest_drink"] = latest_drink

            except (KeyError, TypeError, IndexError):
                logger.warning(
                    "no water remaining/change events found in household timeline "
                    "(checked last %s entries)",
                    len(household_timeline) or 0,
                )

        return latest_drink

    async def get_household_timeline(
        self, household_id: int | None = None, entries: int = 25
    ) -> list[dict[str, Any]]:
        """Fetch Felaqua water level information."""

        # pagination as the api gives us at most 25 results per page
        max_entries_per_page = 25
        pages_to_fetch = ceil(entries / max_entries_per_page)

        current_page = 1
        household_timeline = []

        while current_page <= pages_to_fetch:

            resource = HOUSEHOLD_TIMELINE_RESOURCE.format(
                BASE_RESOURCE=BASE_RESOURCE,
                household_id=household_id,
                page=current_page,
                page_size=max_entries_per_page,
            )

            if timeline := await self.sac.call(method="GET", resource=resource):
                household_timeline += timeline.get("data", [])

            current_page += 1

        return household_timeline

    async def get_timeline(self) -> dict[str, Any]:
        """Retrieve the flap data/state."""
        return await self.sac.call(method="GET", resource=TIMELINE_RESOURCE) or {}

    async def get_notification(self) -> dict[str, Any] | None:
        """Retrieve the flap data/state."""
        return await self.sac.call(
            method="GET", resource=NOTIFICATION_RESOURCE, timeout=API_TIMEOUT * 2
        )

    async def get_report(self, household_id: int, pet_id: int | None = None) -> dict[str, Any]:
        """Retrieve the pet/household report."""
        return (
            await self.sac.call(
                method="GET",
                resource=f"{BASE_RESOURCE}/report/household/{household_id}/pet/{pet_id}",
            )
            if pet_id
            else await self.sac.call(
                method="GET", resource=f"{BASE_RESOURCE}/report/household/{household_id}"
            )
        ) or {}

    async def get_pet(self, pet_id: int) -> Pet | None:
        if pet_id not in self.entities:
            await self.get_entities()

        if self.entities[pet_id].type == EntityType.PET:
            return self.entities[pet_id]  # type: ignore
        else:
            return None

    async def get_pets(self) -> list[Pet]:
        return [pet for pet in (await self.get_entities()).values() if isinstance(pet, Pet)]

    async def get_device(self, device_id: int) -> SurepyDevice | None:
        if device_id not in self.entities:
            await self.get_entities()

        if self.entities[device_id].type != EntityType.PET:
            return self.entities[device_id]  # type: ignore
        else:
            return None

    async def get_devices(self) -> list[SurepyDevice]:
        return [
            device
            for device in (await self.get_entities()).values()
            if isinstance(device, SurepyDevice)
        ]

    async def get_attributes(self) -> dict[str, Any] | None:
        # fetch additional data from sure petcare
        attributes: dict[str, Any] | None = None

        if (raw_data := (await self.sac.call(method="GET", resource=ATTR_RESOURCE))) and (
            attributes := raw_data.get("data")
        ):

            for breed in attributes.get("breed", {}):
                self._breeds[breed["id"]] = breed["name"]

                if breed["species_id"] not in self._breeds:
                    self._species_breeds[breed["species_id"]] = {}

                self._species_breeds[breed["species_id"]][breed["id"]] = breed["name"]

            for condition in attributes.get("condition", {}):
                self._conditions[condition["id"]] = condition["name"]

        return attributes

    async def get_entities(self, refresh: bool = False) -> dict[int, SurepyEntity]:
        """Get all Entities (Pets/Devices)"""

        household_ids: set[int] = set()
        felaqua_household_ids: set[int] = set()
        surepy_entities: dict[int, SurepyEntity] = {}

        raw_data: dict[str, list[dict[str, Any]]] = {}

        # get data like species, breed, conditions
        # await self.get_attributes()

        if MESTART_RESOURCE not in self.sac.resources or refresh:
            if response := await self.sac.call(method="GET", resource=MESTART_RESOURCE):
                raw_data = response.get("data", {})
        else:
            raw_data = self.sac.resources[MESTART_RESOURCE].get("data", {})

        if not raw_data:
            logger.error("could not fetch data ¯\\_(ツ)_/¯")
            return surepy_entities

        all_entities = raw_data.get("devices", []) + raw_data.get("pets", [])

        for entity in all_entities:

            # key used by sure petcare in api response
            entity_type = EntityType(int(entity.get("product_id", 0)))
            entity_id = entity["id"]

            if entity_type in [EntityType.CAT_FLAP, EntityType.PET_FLAP]:
                surepy_entities[entity_id] = Flap(data=entity)
            elif entity_type in [EntityType.FEEDER, EntityType.FEEDER_LITE]:
                surepy_entities[entity_id] = Feeder(data=entity)
            elif entity_type == EntityType.FELAQUA:
                surepy_entities[entity_id] = Felaqua(data=entity)
                felaqua_household_ids.add(int(surepy_entities[entity_id].household_id))
            elif entity_type == EntityType.HUB:
                surepy_entities[entity_id] = Hub(data=entity)
            elif entity_type == EntityType.PET:
                surepy_entities[entity_id] = Pet(data=entity)

            else:
                logger.warning(
                    "unknown type: %s (%s): %s", entity.get("name", "-"), entity_type, entity
                )

            household_ids.add(surepy_entities[entity_id].household_id)

            self.entities[entity_id] = surepy_entities[entity_id]

        # fetch additional data about movement, feeding & drinking
        for household_id in household_ids:
            await self.get_actions(household_id=household_id)
        for household_id in felaqua_household_ids:
            await self.get_latest_anonymous_drinks(household_id=household_id)

        # stupid idea, fix this
        _ = [
            feeder.add_bowls()  # type: ignore
            for feeder in surepy_entities.values()
            if feeder.type == EntityType.FEEDER
        ]

        return self.entities
