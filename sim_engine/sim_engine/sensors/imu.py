"""IMU sensor model."""

from __future__ import annotations

import math
from typing import Any

from geometry_msgs.msg import Quaternion, Vector3
from sensor_msgs.msg import Imu
from std_msgs.msg import Header

from sim_engine.agent import Agent
from sim_engine.sensors import (
    QoSPreset,
    SensorModel,
    TopicConfig,
    register_sensor,
)
from sim_engine.world_state import WorldState


def euler_to_quaternion(roll: float, pitch: float, yaw: float) -> Quaternion:
    """Convert Euler angles (radians) to a geometry_msgs Quaternion."""
    cr, sr = math.cos(roll / 2), math.sin(roll / 2)
    cp, sp = math.cos(pitch / 2), math.sin(pitch / 2)
    cy, sy = math.cos(yaw / 2), math.sin(yaw / 2)

    q = Quaternion()
    q.w = cr * cp * cy + sr * sp * sy
    q.x = sr * cp * cy - cr * sp * sy
    q.y = cr * sp * cy + sr * cp * sy
    q.z = cr * cp * sy - sr * sp * cy
    return q


@register_sensor("imu")
class ImuModel(SensorModel):
    """Simulates an IMU publishing sensor_msgs/Imu.

    Produces orientation (from agent pose), angular velocity, and linear
    acceleration (gravity + noise). Noise is additive Gaussian on each axis.
    """

    GRAVITY = 9.80665

    def __init__(self) -> None:
        super().__init__()
        self._accel_std: float = 0.01
        self._gyro_std: float = 0.001
        self._orientation_std: float = 0.005
        self._topic_suffix: str = "imu/data"

    def configure(self, params: dict[str, Any]) -> None:
        self._rate_hz = params.get("rate_hz", 50.0)
        self._topic_suffix = params.get("topic_suffix", "imu/data")
        noise = params.get("noise", {})
        self._accel_std = noise.get("accel_std", 0.01)
        self._gyro_std = noise.get("gyro_std", 0.001)
        self._orientation_std = noise.get("orientation_std", 0.005)
        if "seed" in params:
            self.set_seed(params["seed"])

    def get_topic_config(self) -> TopicConfig:
        return TopicConfig(
            suffix=self._topic_suffix,
            msg_type=Imu,
            qos=QoSPreset.SENSOR_DATA,
        )

    def update(
        self,
        agent: Agent,
        world: WorldState,
        dt: float,
    ) -> Imu | None:
        if not self.should_publish(dt):
            return None

        msg = Imu()
        msg.header = Header()
        msg.header.stamp.sec = int(world.sim_time_ns // 1_000_000_000)
        msg.header.stamp.nanosec = int(world.sim_time_ns % 1_000_000_000)
        msg.header.frame_id = f"{agent.agent_name}/imu_link"

        # Orientation from agent pose with noise
        noisy_roll = agent.pose.roll + self.gauss(0.0, self._orientation_std)
        noisy_pitch = agent.pose.pitch + self.gauss(0.0, self._orientation_std)
        noisy_yaw = agent.pose.heading + self.gauss(0.0, self._orientation_std)
        msg.orientation = euler_to_quaternion(noisy_roll, noisy_pitch, noisy_yaw)
        o_var = self._orientation_std**2
        msg.orientation_covariance = [
            o_var, 0.0, 0.0,
            0.0, o_var, 0.0,
            0.0, 0.0, o_var,
        ]

        # Angular velocity from agent velocity state with noise
        msg.angular_velocity = Vector3(
            x=agent.velocity.wx + self.gauss(0.0, self._gyro_std),
            y=agent.velocity.wy + self.gauss(0.0, self._gyro_std),
            z=agent.velocity.wz + self.gauss(0.0, self._gyro_std),
        )
        g_var = self._gyro_std**2
        msg.angular_velocity_covariance = [
            g_var, 0.0, 0.0,
            0.0, g_var, 0.0,
            0.0, 0.0, g_var,
        ]

        # Linear acceleration: gravity in body frame + noise
        # For a level vehicle, gravity is [0, 0, +g] in body z-up
        # We rotate gravity into body frame based on roll/pitch
        sr, cr = math.sin(agent.pose.roll), math.cos(agent.pose.roll)
        sp, cp = math.sin(agent.pose.pitch), math.cos(agent.pose.pitch)

        msg.linear_acceleration = Vector3(
            x=-self.GRAVITY * sp + self.gauss(0.0, self._accel_std),
            y=self.GRAVITY * sr * cp + self.gauss(0.0, self._accel_std),
            z=self.GRAVITY * cr * cp + self.gauss(0.0, self._accel_std),
        )
        a_var = self._accel_std**2
        msg.linear_acceleration_covariance = [
            a_var, 0.0, 0.0,
            0.0, a_var, 0.0,
            0.0, 0.0, a_var,
        ]

        return msg

    def get_config(self) -> dict[str, Any]:
        base = super().get_config()
        base["topic_suffix"] = self._topic_suffix
        base["noise"] = {
            "accel_std": self._accel_std,
            "gyro_std": self._gyro_std,
            "orientation_std": self._orientation_std,
        }
        return base
