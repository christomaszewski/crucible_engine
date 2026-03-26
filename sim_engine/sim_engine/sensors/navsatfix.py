"""NavSatFix (GPS) sensor model."""

from __future__ import annotations

from typing import Any

from sensor_msgs.msg import NavSatFix, NavSatStatus
from std_msgs.msg import Header

from sim_engine.agent import Agent
from sim_engine.sensors import (
    QoSPreset,
    SensorModel,
    TopicConfig,
    register_sensor,
)
from sim_engine.world_state import WorldState

# Approximate meters-per-degree at mid latitudes
_M_PER_DEG_LAT = 111_320.0
_M_PER_DEG_LON_AT_45 = 78_710.0


@register_sensor("navsatfix")
class NavSatFixModel(SensorModel):
    """Simulates a GPS receiver publishing sensor_msgs/NavSatFix."""

    def __init__(self) -> None:
        super().__init__()
        self._horizontal_std_m: float = 1.5
        self._vertical_std_m: float = 3.0
        self._topic_suffix: str = "gps/fix"

    def configure(self, params: dict[str, Any]) -> None:
        self._rate_hz = params.get("rate_hz", 5.0)
        self._topic_suffix = params.get("topic_suffix", "gps/fix")
        noise = params.get("noise", {})
        self._horizontal_std_m = noise.get("horizontal_std_m", 1.5)
        self._vertical_std_m = noise.get("vertical_std_m", 3.0)
        if "seed" in params:
            self.set_seed(params["seed"])

    def get_topic_config(self) -> TopicConfig:
        return TopicConfig(
            suffix=self._topic_suffix,
            msg_type=NavSatFix,
            qos=QoSPreset.SENSOR_DATA,
        )

    def update(
        self,
        agent: Agent,
        world: WorldState,
        dt: float,
    ) -> NavSatFix | None:
        if not self.should_publish(dt):
            return None

        import math

        cos_lat = math.cos(math.radians(agent.pose.latitude))
        m_per_deg_lon = _M_PER_DEG_LAT * cos_lat

        noise_north_m = self.gauss(0.0, self._horizontal_std_m)
        noise_east_m = self.gauss(0.0, self._horizontal_std_m)
        noise_alt_m = self.gauss(0.0, self._vertical_std_m)

        msg = NavSatFix()
        msg.header = Header()
        msg.header.stamp.sec = int(world.sim_time_ns // 1_000_000_000)
        msg.header.stamp.nanosec = int(world.sim_time_ns % 1_000_000_000)
        msg.header.frame_id = f"{agent.agent_id}/gps"

        msg.status.status = NavSatStatus.STATUS_FIX
        msg.status.service = NavSatStatus.SERVICE_GPS

        msg.latitude = agent.pose.latitude + (noise_north_m / _M_PER_DEG_LAT)
        msg.longitude = agent.pose.longitude + (noise_east_m / m_per_deg_lon)
        msg.altitude = agent.pose.altitude + noise_alt_m

        # Covariance (ENU, diagonal, meters^2)
        h_var = self._horizontal_std_m**2
        v_var = self._vertical_std_m**2
        msg.position_covariance = [
            h_var, 0.0, 0.0,
            0.0, h_var, 0.0,
            0.0, 0.0, v_var,
        ]
        msg.position_covariance_type = NavSatFix.COVARIANCE_TYPE_DIAGONAL_KNOWN

        return msg

    def get_config(self) -> dict[str, Any]:
        base = super().get_config()
        base["topic_suffix"] = self._topic_suffix
        base["noise"] = {
            "horizontal_std_m": self._horizontal_std_m,
            "vertical_std_m": self._vertical_std_m,
        }
        return base
