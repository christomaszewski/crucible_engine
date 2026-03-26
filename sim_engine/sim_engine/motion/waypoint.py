"""Waypoint trajectory motion model — agent follows a predefined path."""

from __future__ import annotations

import math
from typing import Any

from sim_engine.agent import Agent, Pose
from sim_engine.motion import MotionModel, register_motion
from sim_engine.world_state import WorldState

_M_PER_DEG_LAT = 111_320.0


@register_motion("waypoint")
class WaypointMotionModel(MotionModel):
    """Moves agent along a sequence of waypoints at a fixed speed.

    Waypoints are specified as a list of {lat, lon, alt} dicts. The agent
    moves toward each waypoint in order, advancing to the next when within
    the arrival threshold. Optionally loops back to the first waypoint.
    """

    def __init__(self) -> None:
        self._waypoints: list[Pose] = []
        self._speed_mps: float = 5.0
        self._arrival_threshold_m: float = 2.0
        self._loop: bool = False
        self._current_idx: int = 0

    def configure(self, params: dict[str, Any]) -> None:
        self._speed_mps = params.get("speed_mps", 5.0)
        self._arrival_threshold_m = params.get("arrival_threshold_m", 2.0)
        self._loop = params.get("loop", False)
        self._current_idx = 0

        self._waypoints = []
        for wp in params.get("waypoints", []):
            self._waypoints.append(
                Pose(
                    latitude=wp["lat"],
                    longitude=wp["lon"],
                    altitude=wp.get("alt", 0.0),
                )
            )

    def step(self, agent: Agent, world: WorldState, dt: float) -> None:
        if not self._waypoints or self._current_idx >= len(self._waypoints):
            return

        target = self._waypoints[self._current_idx]
        dist = agent.pose.distance_3d_to(target)

        # Check arrival
        if dist < self._arrival_threshold_m:
            self._current_idx += 1
            if self._loop and self._current_idx >= len(self._waypoints):
                self._current_idx = 0
            return

        # Compute direction and move
        dlat = target.latitude - agent.pose.latitude
        dlon = target.longitude - agent.pose.longitude
        dalt = target.altitude - agent.pose.altitude

        cos_lat = math.cos(math.radians(agent.pose.latitude))
        north_m = dlat * _M_PER_DEG_LAT
        east_m = dlon * _M_PER_DEG_LAT * cos_lat

        horiz_dist = math.sqrt(north_m**2 + east_m**2)
        total_dist = math.sqrt(horiz_dist**2 + dalt**2)

        if total_dist < 1e-9:
            return

        # Normalize and scale by speed * dt
        step_m = min(self._speed_mps * dt, total_dist)
        scale = step_m / total_dist

        agent.pose.latitude += (dlat * scale)
        agent.pose.longitude += (dlon * scale)
        agent.pose.altitude += (dalt * scale)

        # Update heading to face direction of travel
        agent.pose.heading = math.atan2(east_m, north_m)

        # Update velocity state
        agent.velocity.vx = self._speed_mps * (north_m / max(horiz_dist, 1e-9))
        agent.velocity.vy = self._speed_mps * (east_m / max(horiz_dist, 1e-9))
        agent.velocity.vz = self._speed_mps * (dalt / max(total_dist, 1e-9))

    def get_config(self) -> dict[str, Any]:
        base = super().get_config()
        base["speed_mps"] = self._speed_mps
        base["arrival_threshold_m"] = self._arrival_threshold_m
        base["loop"] = self._loop
        base["waypoints"] = [
            {"lat": wp.latitude, "lon": wp.longitude, "alt": wp.altitude}
            for wp in self._waypoints
        ]
        return base
