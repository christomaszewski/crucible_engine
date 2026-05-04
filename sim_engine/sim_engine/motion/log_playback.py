"""Log-playback motion model — pose driven by ROS2 messages from a played-back bag."""

from __future__ import annotations

import math
from typing import Any

from sensor_msgs.msg import Imu, NavSatFix

from sim_engine.agent import Agent
from sim_engine.motion import MotionModel, register_motion
from sim_engine.world_state import WorldState

_M_PER_DEG_LAT = 111_320.0


@register_motion("log_playback")
class LogPlaybackMotionModel(MotionModel):
    """Drives agent pose from played-back log topics.

    Subscribes to a position topic (NavSatFix) and optionally an orientation
    topic (IMU). The latest received message is applied to the agent's pose
    on each step. Velocity is estimated from successive position updates so
    ground truth has a reasonable velocity field.

    Topics may be specified as a suffix (relative to /<agent_name>/) or as
    an absolute path with a leading slash.
    """

    def __init__(self) -> None:
        self._position_topic: str = "gps/fix"
        self._orientation_topic: str | None = None

        # Latest received (lat, lon, alt) — None until first msg
        self._latest_position: tuple[float, float, float] | None = None
        # Pending position to apply on next step (consumed by step)
        self._pending_position: tuple[float, float, float] | None = None
        # For velocity estimation: previous position + sim time at that step
        self._prev_position: tuple[float, float, float] | None = None
        self._time_since_prev: float = 0.0

        # Latest received orientation as (roll, pitch, yaw) in radians
        self._latest_orientation: tuple[float, float, float] | None = None
        self._pending_orientation: tuple[float, float, float] | None = None

    # -- Configuration -------------------------------------------------------

    def configure(self, params: dict[str, Any]) -> None:
        self._position_topic = params.get("position_topic", "gps/fix")
        self._orientation_topic = params.get("orientation_topic")

    @property
    def position_topic(self) -> str:
        return self._position_topic

    @property
    def orientation_topic(self) -> str | None:
        return self._orientation_topic

    def resolve_topic(self, agent_name: str, topic: str) -> str:
        """Resolve a topic suffix to a full ROS2 topic for the given agent."""
        if topic.startswith("/"):
            return topic
        return f"/{agent_name}/{topic}"

    # -- Subscription callbacks (invoked by the sim engine node) -------------

    def on_position(self, msg: NavSatFix) -> None:
        """Receive a NavSatFix message and stage it for the next step."""
        self._pending_position = (msg.latitude, msg.longitude, msg.altitude)

    def on_orientation(self, msg: Imu) -> None:
        """Receive an Imu message and stage its orientation for the next step."""
        q = msg.orientation
        # Quaternion → roll/pitch/yaw (Tait-Bryan, ZYX, intrinsic)
        sinr_cosp = 2.0 * (q.w * q.x + q.y * q.z)
        cosr_cosp = 1.0 - 2.0 * (q.x * q.x + q.y * q.y)
        roll = math.atan2(sinr_cosp, cosr_cosp)

        sinp = 2.0 * (q.w * q.y - q.z * q.x)
        if abs(sinp) >= 1.0:
            pitch = math.copysign(math.pi / 2.0, sinp)
        else:
            pitch = math.asin(sinp)

        siny_cosp = 2.0 * (q.w * q.z + q.x * q.y)
        cosy_cosp = 1.0 - 2.0 * (q.y * q.y + q.z * q.z)
        yaw = math.atan2(siny_cosp, cosy_cosp)

        self._pending_orientation = (roll, pitch, yaw)

    # -- Sim loop integration ------------------------------------------------

    def step(self, agent: Agent, world: WorldState, dt: float) -> None:
        # Apply latest orientation if any arrived since last step
        if self._pending_orientation is not None:
            roll, pitch, yaw = self._pending_orientation
            agent.pose.roll = roll
            agent.pose.pitch = pitch
            agent.pose.heading = yaw
            self._latest_orientation = self._pending_orientation
            self._pending_orientation = None

        # Apply latest position if any arrived since last step; estimate velocity
        if self._pending_position is not None:
            lat, lon, alt = self._pending_position
            agent.pose.latitude = lat
            agent.pose.longitude = lon
            agent.pose.altitude = alt

            interval = self._time_since_prev + dt
            if self._prev_position is not None and interval > 0.0:
                prev_lat, prev_lon, prev_alt = self._prev_position
                cos_lat = math.cos(math.radians(lat))
                north_m = (lat - prev_lat) * _M_PER_DEG_LAT
                east_m = (lon - prev_lon) * _M_PER_DEG_LAT * cos_lat
                up_m = alt - prev_alt
                agent.velocity.vx = north_m / interval
                agent.velocity.vy = east_m / interval
                agent.velocity.vz = -up_m / interval  # body z-down convention

            self._prev_position = self._pending_position
            self._latest_position = self._pending_position
            self._pending_position = None
            self._time_since_prev = 0.0
        else:
            self._time_since_prev += dt

    def get_config(self) -> dict[str, Any]:
        base = super().get_config()
        base["position_topic"] = self._position_topic
        if self._orientation_topic is not None:
            base["orientation_topic"] = self._orientation_topic
        return base
