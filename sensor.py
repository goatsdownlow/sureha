"""Support for Sure PetCare Flaps/Pets sensors."""
from __future__ import annotations

import logging
from typing import Any, cast

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_VOLTAGE,
    DEVICE_CLASS_BATTERY,
    MASS_GRAMS,
    PERCENTAGE,
    VOLUME_MILLILITERS,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from surepy.entities import SurepyEntity
from surepy.entities.devices import (
    Feeder as SureFeeder,
    FeederBowl as SureFeederBowl,
    Felaqua as SureFelaqua,
    Flap as SureFlap,
    SurepyDevice,
)
from surepy.enums import EntityType, LockState

# pylint: disable=relative-beyond-top-level
from . import SurePetcareAPI
from .const import DOMAIN, SPC, SURE_MANUFACTURER

PARALLEL_UPDATES = 2


_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigEntry,
    async_add_entities: Any,
    discovery_info: Any = None,
) -> None:
    """Set up Sure PetCare sensor platform."""
    await async_setup_entry(hass, config, async_add_entities)


async def async_setup_entry(
    hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities: Any
) -> None:
    """Set up config entry Sure PetCare Flaps sensors."""

    entities: list[Flap | Felaqua | Feeder | FeederBowl | Battery] = []

    spc: SurePetcareAPI = hass.data[DOMAIN][SPC]

    for surepy_entity in spc.coordinator.data.values():

        if surepy_entity.type in [
            EntityType.CAT_FLAP,
            EntityType.PET_FLAP,
        ]:
            entities.append(Flap(spc.coordinator, surepy_entity.id, spc))

        elif surepy_entity.type == EntityType.FELAQUA:
            entities.append(Felaqua(spc.coordinator, surepy_entity.id, spc))

        elif surepy_entity.type == EntityType.FEEDER:

            for bowl in surepy_entity.bowls.values():
                entities.append(
                    FeederBowl(spc.coordinator, surepy_entity.id, spc, bowl.raw_data())
                )

            entities.append(Feeder(spc.coordinator, surepy_entity.id, spc))

        if surepy_entity.type in [
            EntityType.CAT_FLAP,
            EntityType.PET_FLAP,
            EntityType.FEEDER,
            EntityType.FELAQUA,
        ]:
            entities.append(Battery(spc.coordinator, surepy_entity.id, spc))

    async_add_entities(entities)


class SurePetcareSensor(CoordinatorEntity, SensorEntity):
    """A binary sensor implementation for Sure Petcare Entities."""

    _attr_should_poll = False

    def __init__(self, coordinator, _id: int, spc: SurePetcareAPI):
        """Initialize a Sure Petcare sensor."""
        super().__init__(coordinator)

        self._id = _id
        self._spc: SurePetcareAPI = spc

        self._coordinator = coordinator

        self._surepy_entity: SurepyEntity = self._coordinator.data[_id]
        self._state: dict[str, Any] = self._surepy_entity.raw_data()["status"]

        self._attr_available = bool(self._state)
        self._attr_unique_id = f"{self._surepy_entity.household_id}-{self._id}"

        self._attr_extra_state_attributes = (
            {**self._surepy_entity.raw_data()} if self._state else {}
        )

        self._attr_name: str = (
            f"{self._surepy_entity.type.name.replace('_', ' ').title()} "
            f"{self._surepy_entity.name.capitalize()}"
        )

    @property
    def device_info(self):

        device = {}

        try:
            model = f"{self._surepy_entity.type.name.replace('_', ' ').title()}"

            if serial := self._surepy_entity.raw_data().get("serial_number", None):
                model = f"{model} ({serial})"

            device = {
                "identifiers": {(DOMAIN, self._id)},
                "name": self._surepy_entity.name.capitalize(),
                "manufacturer": SURE_MANUFACTURER,
                "model": model,
            }

            if self._surepy_entity:
                versions = self._state.get("version", {})

                if dev_fw_version := versions.get("device", {}).get("firmware"):
                    device["sw_version"] = dev_fw_version

                if (lcd_version := versions.get("lcd", {})) and (
                    rf_version := versions.get("rf", {})
                ):
                    device["sw_version"] = (
                        f"lcd: {lcd_version.get('version', lcd_version)['firmware']} | "
                        f"fw: {rf_version.get('version', rf_version)['firmware']}"
                    )

        except AttributeError:
            pass

        return device


class Flap(SurePetcareSensor):
    """Sure Petcare Flap."""

    def __init__(self, coordinator, _id: int, spc: SurePetcareAPI) -> None:
        super().__init__(coordinator, _id, spc)

        self._surepy_entity: SureFlap

        self._attr_entity_picture = self._surepy_entity.icon
        self._attr_unit_of_measurement = None

        if self._state:
            self._attr_extra_state_attributes = {
                "learn_mode": bool(self._state["learn_mode"]),
                **self._surepy_entity.raw_data(),
            }

            if locking := self._state.get("locking"):
                self._attr_state = LockState(locking["mode"]).name.casefold()

    @property
    def state(self) -> str:
        """Return battery level in percent."""
        if (
            state := cast(SureFlap, self.coordinator.data[self._id])
            .raw_data()
            .get("status")
        ):
            return LockState(state["locking"]["mode"]).name.casefold()

        return "Unknown"


class Felaqua(SurePetcareSensor):
    """Sure Petcare Felaqua."""

    def __init__(self, coordinator, _id: int, spc: SurePetcareAPI):
        super().__init__(coordinator, _id, spc)

        self._surepy_entity: SureFelaqua
        self._attr_entity_picture = self._surepy_entity.icon
        self._attr_unit_of_measurement = VOLUME_MILLILITERS

    @property
    def state(self) -> int | None:
        """Return the remaining water."""
        if felaqua := cast(SureFelaqua, self.coordinator.data[self._id]):
            return max(0, int(felaqua.water_remaining or 0))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the remaining water."""

        attrs = {}

        if (
            state := cast(SureFelaqua, self.coordinator.data[self._id])
            .raw_data()
            .get("status")
        ):
            for weight in state.get("drink", {}).get("weights", {}):
                attr_key = f"weight_{weight['index']}"
                attrs[attr_key] = weight

        return attrs

    @property
    def device_info(self):

        device = {}

        if felaqua := cast(SureFelaqua, self.coordinator.data[self._id]):

            try:
                model = f"{felaqua.type.name.replace('_', ' ').title()}"

                if serial := felaqua.raw_data().get("serial_number", None):
                    model = f"{model} ({serial})"

                device = {
                    "identifiers": {(DOMAIN, self._id)},
                    "name": felaqua.name.capitalize(),
                    "manufacturer": SURE_MANUFACTURER,
                    "model": model,
                }

            except AttributeError:
                pass

        return device


class FeederBowl(SurePetcareSensor):
    """Sure Petcare Feeder Bowl."""

    def __init__(
        self,
        coordinator,
        _id: int,
        spc: SurePetcareAPI,
        bowl_data: dict[str, int | str],
    ):
        """Initialize a Bowl sensor."""
        super().__init__(coordinator, _id, spc)

        self.feeder_id = _id
        self.bowl_id = int(bowl_data["index"])

        self._id = int(f"{_id}{str(self.bowl_id)}")
        self._spc: SurePetcareAPI = spc

        self._surepy_feeder_entity: SurepyEntity = self._coordinator.data[_id]
        self._surepy_entity: SureFeederBowl = self._coordinator.data[_id].bowls[
            self.bowl_id
        ]
        self._state: dict[str, Any] = bowl_data

        # https://github.com/PyCQA/pylint/issues/2062
        # pylint: disable=no-member
        self._attr_name = (
            f"{EntityType.FEEDER.name.replace('_', ' ').title()} "
            f"{self._surepy_entity.name.capitalize()}"
        )

        self._attr_icon = "mdi:bowl"
        self._attr_state = int(self._surepy_entity.weight)
        self._attr_unique_id = (
            f"{self._surepy_feeder_entity.household_id}-{self.feeder_id}-{self.bowl_id}"
        )
        self._attr_unit_of_measurement = MASS_GRAMS

    @property
    def state(self) -> int | None:
        """Return the remaining water."""
        if feeder := cast(SureFeeder, self.coordinator.data[self.feeder_id]):
            return max(0, int(feeder.bowls[self.bowl_id].weight))


class Feeder(SurePetcareSensor):
    """Sure Petcare Feeder."""

    def __init__(self, coordinator, _id: int, spc: SurePetcareAPI):
        super().__init__(coordinator, _id, spc)

        self._surepy_entity: SureFeeder
        self._attr_entity_picture = self._surepy_entity.icon
        self._attr_unit_of_measurement = MASS_GRAMS

    @property
    def state(self) -> int | None:
        """Return the total remaining food."""
        if feeder := cast(SureFeeder, self.coordinator.data[self._id]):
            return int(feeder.total_weight)

    @property
    def device_info(self):

        device = {}

        try:
            model = f"{self._surepy_entity.type.name.replace('_', ' ').title()}"

            if serial := self._surepy_entity.raw_data().get("serial_number", None):
                model = f"{model} ({serial})"

            device = {
                "identifiers": {(DOMAIN, self._id)},
                "name": self._surepy_entity.name.capitalize(),
                "manufacturer": SURE_MANUFACTURER,
                "model": model,
            }

        except AttributeError:
            pass

        return device


class Battery(SurePetcareSensor):
    """Sure Petcare Flap."""

    def __init__(self, coordinator, _id: int, spc: SurePetcareAPI):
        super().__init__(coordinator, _id, spc)

        self._surepy_entity: SurepyDevice

        self._attr_name = f"{self._attr_name} Battery Level"
        self._attr_unit_of_measurement = PERCENTAGE

        self._attr_device_class = DEVICE_CLASS_BATTERY
        self._attr_unique_id = (
            f"{self._surepy_entity.household_id}-{self._surepy_entity.id}-battery"
        )

    @property
    def state(self) -> int | None:
        """Return battery level in percent."""
        if (
            battery := cast(SurepyDevice, self.coordinator.data[self._id])
        ) and battery.battery_level:
            return max(0, battery.battery_level)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the additional attrs."""

        attrs = {}

        if (
            state := cast(SurepyDevice, self.coordinator.data[self._id])
            .raw_data()
            .get("status")
        ):
            voltage_per_battery = float(state["battery"]) / 4
            attrs = {
                ATTR_VOLTAGE: f"{float(state['battery']):.2f}",
                f"{ATTR_VOLTAGE}_per_battery": f"{voltage_per_battery:.2f}",
                "alt-battery": (1 - pow(6 - float(state["battery"]), 2)) * 100,
            }

        return attrs
