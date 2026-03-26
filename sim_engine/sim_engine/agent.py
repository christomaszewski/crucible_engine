"""Agent state representation for the simulation."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sim_engine.motion import MotionModel
    from sim_engine.sensors import SensorModel


@dataclass
class Pose:
    """Geodetic pose with orientation."""

    latitude: float = 0.0
    longitude: float = 0.0
    altitude: float = 0.0
    heading: float = 0.0  # radians, 0 = north, CW positive
    pitch: float = 0.0
    roll: float = 0.0

    def distance_to(self, other: Pose) -> float:
        """Haversine distance in meters to another pose."""
        r = 6_371_000.0
        lat1 = math.radians(self.latitude)
        lat2 = math.radians(other.latitude)
        dlat = lat2 - lat1
        dlon = math.radians(other.longitude - self.longitude)

        a = (
            math.sin(dlat / 2.0) ** 2
            + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2.0) ** 2
        )
        return r * 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))

    def distance_3d_to(self, other: Pose) -> float:
        """3D distance in meters including altitude."""
        horiz = self.distance_to(other)
        dalt = other.altitude - self.altitude
        return math.sqrt(horiz**2 + dalt**2)


@dataclass
class Velocity:
    """Body-frame velocity state."""

    vx: float = 0.0  # forward (m/s)
    vy: float = 0.0  # right (m/s)
    vz: float = 0.0  # down (m/s)
    wx: float = 0.0  # roll rate (rad/s)
    wy: float = 0.0  # pitch rate (rad/s)
    wz: float = 0.0  # yaw rate (rad/s)


@dataclass
class Agent:
    """A simulated agent with pose, velocity, sensors, and motion model."""

    agent_id: str
    pose: Pose = field(default_factory=Pose)
    velocity: Velocity = field(default_factory=Velocity)
    domain_id: int = 0
    vehicle_type: str = ""
    vehicle_class: str = ""
    sensors: dict[str, SensorModel] = field(default_factory=dict)
    motion_model: MotionModel | None = None

    # Stack orchestration config (optional)
    stack_compose_file: str | None = None
    stack_env: dict[str, str] = field(default_factory=dict)
    stack_auto_launch: bool = False

    # Pose estimate subscription topic (optional)
    pose_estimate_topic: str | None = None
