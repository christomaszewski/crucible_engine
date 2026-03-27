"""Scenario event timeline runner."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from sim_engine.world_state import WorldState

logger = logging.getLogger(__name__)


@dataclass
class ScenarioEvent:
    """A timed event in the simulation scenario."""

    time_s: float
    action: str
    params: dict[str, Any] = field(default_factory=dict)
    fired: bool = False


class ScenarioRunner:
    """Executes scenario events at the correct sim time.

    Events are sorted by time and fired in order as sim time advances.
    Each event type maps to a handler method.
    """

    def __init__(self, world: WorldState) -> None:
        self._world = world
        self._events: list[ScenarioEvent] = []

    def load_events(self, event_defs: list[dict[str, Any]]) -> None:
        """Load events from config dicts."""
        self._events = []
        for edef in event_defs:
            params = {k: v for k, v in edef.items() if k not in ("time_s", "action")}
            self._events.append(
                ScenarioEvent(
                    time_s=edef["time_s"],
                    action=edef["action"],
                    params=params,
                )
            )
        self._events.sort(key=lambda e: e.time_s)

    def reset(self) -> None:
        """Reset all events to unfired state."""
        for event in self._events:
            event.fired = False

    def tick(self, sim_time_s: float) -> list[ScenarioEvent]:
        """Check and fire any events whose time has arrived.

        Returns the list of events that fired this tick.
        """
        fired: list[ScenarioEvent] = []

        for event in self._events:
            if event.fired:
                continue
            if sim_time_s < event.time_s:
                break  # events are sorted, no more to check
            event.fired = True
            self._execute(event)
            fired.append(event)

        return fired

    def _execute(self, event: ScenarioEvent) -> None:
        """Dispatch an event to the appropriate handler."""
        handler = getattr(self, f"_handle_{event.action}", None)
        if handler is None:
            logger.warning("Unknown scenario event action: %s", event.action)
            return
        try:
            handler(event.params)
        except Exception:
            logger.exception("Failed to execute scenario event: %s", event)

    def _handle_disable_sensor(self, params: dict[str, Any]) -> None:
        agent_name = params["agent"]
        sensor_name = params["sensor"]
        agent = self._world.get_agent(agent_name)
        if sensor_name in agent.sensors:
            del agent.sensors[sensor_name]
            logger.info("Disabled sensor %s on %s", sensor_name, agent_name)

    def _handle_enable_sensor(self, params: dict[str, Any]) -> None:
        # Re-enabling requires reconstructing the sensor from stored config.
        # For now, log a warning — full implementation needs the config loader.
        logger.warning("enable_sensor not yet fully implemented: %s", params)

    def _handle_update_param(self, params: dict[str, Any]) -> None:
        agent_name = params["agent"]
        sensor_name = params["sensor"]
        param_name = params["param"]
        value = params["value"]

        agent = self._world.get_agent(agent_name)
        sensor = agent.sensors.get(sensor_name)
        if sensor is None:
            logger.warning("Sensor %s not found on %s", sensor_name, agent_name)
            return

        # Update the sensor's internal attribute directly
        attr = f"_{param_name}"
        if hasattr(sensor, attr):
            setattr(sensor, attr, value)
            logger.info(
                "Updated %s.%s = %s on %s",
                sensor_name,
                param_name,
                value,
                agent_name,
            )
        else:
            logger.warning(
                "Sensor %s has no attribute %s", sensor_name, param_name
            )

    def _handle_set_pose(self, params: dict[str, Any]) -> None:
        agent_name = params["agent"]
        agent = self._world.get_agent(agent_name)
        if "lat" in params:
            agent.pose.latitude = params["lat"]
        if "lon" in params:
            agent.pose.longitude = params["lon"]
        if "alt" in params:
            agent.pose.altitude = params["alt"]
        if "heading" in params:
            agent.pose.heading = params["heading"]
        logger.info("Set pose for %s", agent_name)

    def get_events_config(self) -> list[dict[str, Any]]:
        """Serialize events back to config format."""
        result = []
        for event in self._events:
            entry: dict[str, Any] = {
                "time_s": event.time_s,
                "action": event.action,
            }
            entry.update(event.params)
            result.append(entry)
        return result
