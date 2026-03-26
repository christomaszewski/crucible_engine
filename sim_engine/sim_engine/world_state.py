"""World state: agent registry, spatial queries, and environment models."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from sim_engine.agent import Agent

if TYPE_CHECKING:
    from sim_engine.terrain import TerrainModel


class WorldState:
    """Central registry of all agents and environment state.

    Thread-safe via a reentrant lock so service callbacks and the sim loop
    can safely access/mutate agent state concurrently.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._agents: dict[str, Agent] = {}
        self._terrain: TerrainModel | None = None
        self._sim_time_ns: int = 0

    # -- Properties ----------------------------------------------------------

    @property
    def terrain(self) -> TerrainModel | None:
        return self._terrain

    @terrain.setter
    def terrain(self, model: TerrainModel | None) -> None:
        self._terrain = model

    @property
    def sim_time_ns(self) -> int:
        with self._lock:
            return self._sim_time_ns

    @sim_time_ns.setter
    def sim_time_ns(self, value: int) -> None:
        with self._lock:
            self._sim_time_ns = value

    @property
    def sim_time_sec(self) -> float:
        return self.sim_time_ns / 1e9

    # -- Agent registry ------------------------------------------------------

    def add_agent(self, agent: Agent) -> None:
        with self._lock:
            if agent.agent_id in self._agents:
                raise ValueError(f"Agent '{agent.agent_id}' already exists")
            self._agents[agent.agent_id] = agent

    def remove_agent(self, agent_id: str) -> Agent:
        with self._lock:
            if agent_id not in self._agents:
                raise KeyError(f"Agent '{agent_id}' not found")
            return self._agents.pop(agent_id)

    def get_agent(self, agent_id: str) -> Agent:
        with self._lock:
            return self._agents[agent_id]

    def get_all_agents(self) -> list[Agent]:
        with self._lock:
            return list(self._agents.values())

    def agent_exists(self, agent_id: str) -> bool:
        with self._lock:
            return agent_id in self._agents

    # -- Spatial queries -----------------------------------------------------

    def agents_within_range(
        self,
        agent_id: str,
        max_range_m: float,
        sensor_type: str | None = None,
    ) -> list[tuple[Agent, float]]:
        """Return agents within range of the given agent.

        Args:
            agent_id: The reference agent.
            max_range_m: Maximum distance in meters.
            sensor_type: If provided, only return agents that have this sensor
                         type attached.

        Returns:
            List of (agent, distance_m) tuples, sorted by distance.
        """
        with self._lock:
            origin = self._agents[agent_id]
            results: list[tuple[Agent, float]] = []

            for other in self._agents.values():
                if other.agent_id == agent_id:
                    continue
                dist = origin.pose.distance_3d_to(other.pose)
                if dist > max_range_m:
                    continue
                if sensor_type is not None and sensor_type not in other.sensors:
                    continue
                results.append((other, dist))

            results.sort(key=lambda pair: pair[1])
            return results

    def get_terrain_elevation(self, lat: float, lon: float) -> float | None:
        """Query terrain elevation at a position. Returns None if no terrain loaded."""
        if self._terrain is None:
            return None
        return self._terrain.get_elevation(lat, lon)

    # -- Serialization -------------------------------------------------------

    def snapshot(self) -> dict:
        """Return a JSON-serializable snapshot of all agent states."""
        with self._lock:
            return {
                "sim_time_s": self.sim_time_sec,
                "agents": {
                    aid: {
                        "lat": a.pose.latitude,
                        "lon": a.pose.longitude,
                        "alt": a.pose.altitude,
                        "heading": a.pose.heading,
                        "pitch": a.pose.pitch,
                        "roll": a.pose.roll,
                        "sensors": list(a.sensors.keys()),
                        "domain_id": a.domain_id,
                    }
                    for aid, a in self._agents.items()
                },
            }
