"""Commanded velocity motion model — driven by external cmd_vel topic."""

from __future__ import annotations

import math
from typing import Any

from geometry_msgs.msg import Twist

from sim_engine.agent import Agent
from sim_engine.motion import MotionModel, register_motion
from sim_engine.world_state import WorldState

_M_PER_DEG_LAT = 111_320.0


@register_motion("commanded_velocity")
class CommandedVelocityModel(MotionModel):
    """Integrates external Twist commands into agent pose updates.

    Expects a cmd_vel topic to be subscribed by the sim engine node.
    The latest command is stored and integrated each tick.
    """

    def __init__(self) -> None:
        self._max_speed_mps: float = 20.0
        self._topic_suffix: str = "cmd_vel"
        self._latest_cmd: Twist = Twist()

    def configure(self, params: dict[str, Any]) -> None:
        self._max_speed_mps = params.get("max_speed_mps", 20.0)
        self._topic_suffix = params.get("topic_suffix", "cmd_vel")

    @property
    def topic_suffix(self) -> str:
        return self._topic_suffix

    def on_command(self, msg: Twist) -> None:
        """Callback for incoming cmd_vel messages."""
        self._latest_cmd = msg

    def step(self, agent: Agent, world: WorldState, dt: float) -> None:
        cmd = self._latest_cmd

        # Clamp linear speed
        vx = max(-self._max_speed_mps, min(self._max_speed_mps, cmd.linear.x))
        vy = max(-self._max_speed_mps, min(self._max_speed_mps, cmd.linear.y))
        vz = max(-self._max_speed_mps, min(self._max_speed_mps, cmd.linear.z))

        # Update heading from yaw rate
        agent.pose.heading += cmd.angular.z * dt

        # Convert body-frame velocity to geodetic displacement
        cos_h = math.cos(agent.pose.heading)
        sin_h = math.sin(agent.pose.heading)

        # vx = forward (along heading), vy = right (perp to heading)
        north_mps = vx * cos_h - vy * sin_h
        east_mps = vx * sin_h + vy * cos_h

        cos_lat = math.cos(math.radians(agent.pose.latitude))
        m_per_deg_lon = _M_PER_DEG_LAT * cos_lat

        agent.pose.latitude += (north_mps * dt) / _M_PER_DEG_LAT
        agent.pose.longitude += (east_mps * dt) / m_per_deg_lon
        agent.pose.altitude += -vz * dt  # vz positive = down

        # Update velocity state
        agent.velocity.vx = vx
        agent.velocity.vy = vy
        agent.velocity.vz = vz
        agent.velocity.wx = cmd.angular.x
        agent.velocity.wy = cmd.angular.y
        agent.velocity.wz = cmd.angular.z

    def get_config(self) -> dict[str, Any]:
        base = super().get_config()
        base["max_speed_mps"] = self._max_speed_mps
        base["topic_suffix"] = self._topic_suffix
        return base
