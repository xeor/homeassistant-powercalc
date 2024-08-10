from __future__ import annotations

import logging
from _decimal import Decimal

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import CONF_ENTITY_ID, CONF_NAME, CONF_UNIQUE_ID, STATE_UNAVAILABLE, STATE_UNKNOWN, UnitOfPower
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.typing import ConfigType

from custom_components.powercalc.const import (
    CONF_CREATE_ENERGY_SENSORS,
    CONF_POWER_SENSOR_PRECISION,
    CONF_SUBTRACT_ENTITIES,
)
from custom_components.powercalc.sensors.abstract import generate_power_sensor_entity_id, generate_power_sensor_name
from custom_components.powercalc.sensors.energy import create_energy_sensor
from custom_components.powercalc.sensors.group.custom import GroupedSensor
from custom_components.powercalc.sensors.power import PowerSensor

_LOGGER = logging.getLogger(__name__)


async def create_subtract_group_sensors(
    hass: HomeAssistant,
    config: ConfigType,
) -> list[Entity]:
    """Create subtract group sensors."""

    group_name = str(config.get(CONF_NAME))
    base_entity_id = str(config.get(CONF_ENTITY_ID))
    subtract_entities = config.get(CONF_SUBTRACT_ENTITIES)

    name = generate_power_sensor_name(config, group_name)
    unique_id = config.get(CONF_UNIQUE_ID) or f"pc_subtract_{base_entity_id}"
    entity_id = generate_power_sensor_entity_id(
        hass,
        config,
        name=group_name,
        unique_id=unique_id,
    )

    _LOGGER.debug("Creating grouped power sensor: %s (entity_id=%s)", name, entity_id)

    sensors: list[Entity] = []
    power_sensor = SubtractGroupSensor(
        hass,
        group_name,
        config,
        entity_id,
        base_entity_id,
        subtract_entities,  # type: ignore
        unique_id=unique_id,
    )
    sensors.append(power_sensor)
    if config.get(CONF_CREATE_ENERGY_SENSORS):
        sensors.append(
            await create_energy_sensor(
                hass,
                config,
                power_sensor,
            ),
        )
    return sensors


class SubtractGroupSensor(GroupedSensor, PowerSensor):
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfPower.WATT

    def __init__(
        self,
        hass: HomeAssistant,
        name: str,
        sensor_config: ConfigType,
        entity_id: str,
        base_entity_id: str,
        subtract_entities: list[str],
        unique_id: str | None = None,
    ) -> None:
        all_entities = {base_entity_id, *subtract_entities}

        super().__init__(
            hass=hass,
            name=name,
            entities=all_entities,
            entity_id=entity_id,
            sensor_config=sensor_config,
            rounding_digits=int(sensor_config.get(CONF_POWER_SENSOR_PRECISION, 2)),
            unique_id=unique_id,
            device_id=None,  # todo: add device_id
        )

        self._base_entity_id = base_entity_id
        self._subtract_entities = subtract_entities

    def calculate_initial_state(
        self,
        member_available_states: list[State],
        member_states: list[State],
    ) -> Decimal | str:
        self._states = {state.entity_id: self._get_state_value_in_native_unit(state) for state in member_available_states}
        return self.calculate_subtracted()

    def calculate_new_state(self, state: State) -> Decimal | str:
        if state.state in [STATE_UNKNOWN, STATE_UNAVAILABLE]:
            if state.entity_id in self._states:
                del self._states[state.entity_id]
        else:
            self._states[state.entity_id] = self._get_state_value_in_native_unit(state)
        return self.calculate_subtracted()

    def calculate_subtracted(self) -> Decimal | str:
        base_value = self._states.get(self._base_entity_id)
        if base_value is None:
            return STATE_UNKNOWN
        subtracted_value = base_value
        for entity_id in self._subtract_entities:
            subtracted_value -= self._states.get(entity_id, 0)
        return subtracted_value
