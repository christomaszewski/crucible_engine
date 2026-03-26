"""Altimeter sensor model."""

from __future__ import annotations

from typing import Any

from std_msgs.msg import Float64, Header

from sim_engine.agent import Agent
from sim_engine.sensors import (
    QoSPreset,
    SensorModel,
    TopicConfig,
    register_sensor,
)
from sim_engine.world_state import WorldState


@register_sensor("altimeter")
class AltimeterModel(SensorModel):
    """Simulates a barometric altimeter.

    If terrain data is available in the world state, produces AGL (above
    ground level) readings. Otherwise produces MSL altitude readings.
    """

    def __init__(self) -> None:
        super().__init__()
        self._std_m: float = 0.5
        self._topic_suffix: str = "altimeter/data"
        self._use_agl: bool = True

    def configure(self, params: dict[str, Any]) -> None:
        self._rate_hz = params.get("rate_hz", 10.0)
        self._topic_suffix = params.get("topic_suffix", "altimeter/data")
        self._use_agl = params.get("use_agl", True)
        noise = params.get("noise", {})
        self._std_m = noise.get("std_m", 0.5)
        if "seed" in params:
            self.set_seed(params["seed"])

    def get_topic_config(self) -> TopicConfig:
        return TopicConfig(
            suffix=self._topic_suffix,
            msg_type=Float64,
            qos=QoSPreset.SENSOR_DATA,
        )

    def update(
        self,
        agent: Agent,
        world: WorldState,
        dt: float,
    ) -> Float64 | None:
        if not self.should_publish(dt):
            return None

        true_alt = agent.pose.altitude

        if self._use_agl:
            terrain_elev = world.get_terrain_elevation(
                agent.pose.latitude, agent.pose.longitude
            )
            if terrain_elev is not None:
                true_alt = agent.pose.altitude - terrain_elev

        msg = Float64()
        msg.data = true_alt + self.gauss(0.0, self._std_m)
        return msg

    def get_config(self) -> dict[str, Any]:
        base = super().get_config()
        base["topic_suffix"] = self._topic_suffix
        base["use_agl"] = self._use_agl
        base["noise"] = {"std_m": self._std_m}
        return base
