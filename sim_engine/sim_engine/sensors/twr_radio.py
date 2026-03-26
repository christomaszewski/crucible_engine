"""Two-Way Ranging (TWR) mesh radio sensor model.

Simulates time-of-flight ranging between mesh radio nodes. This is NOT UWB —
it models the TWR capability of mesh radios operating at the MAC layer.
"""

from __future__ import annotations

from typing import Any

from sim_msgs.msg import RangeArray, RangeStamped
from std_msgs.msg import Header

from sim_engine.agent import Agent
from sim_engine.sensors import (
    QoSPreset,
    SensorModel,
    TopicConfig,
    register_sensor,
)
from sim_engine.world_state import WorldState


@register_sensor("twr_radio")
class TwrRadioModel(SensorModel):
    """Simulates TWR mesh radio ranging.

    Produces range measurements to all other agents that also have a
    twr_radio sensor and fall within max_range_m. Ranges are corrupted
    with additive Gaussian noise.
    """

    def __init__(self) -> None:
        super().__init__()
        self._max_range_m: float = 500.0
        self._std_m: float = 0.1
        self._topic_suffix: str = "twr/ranges"

    def configure(self, params: dict[str, Any]) -> None:
        self._rate_hz = params.get("rate_hz", 1.0)
        self._topic_suffix = params.get("topic_suffix", "twr/ranges")
        self._max_range_m = params.get("max_range_m", 500.0)
        noise = params.get("noise", {})
        self._std_m = noise.get("std_m", 0.1)
        if "seed" in params:
            self.set_seed(params["seed"])

    def get_topic_config(self) -> TopicConfig:
        return TopicConfig(
            suffix=self._topic_suffix,
            msg_type=RangeArray,
            qos=QoSPreset.SENSOR_DATA,
        )

    def update(
        self,
        agent: Agent,
        world: WorldState,
        dt: float,
    ) -> RangeArray | None:
        if not self.should_publish(dt):
            return None

        neighbors = world.agents_within_range(
            agent.agent_id,
            self._max_range_m,
            sensor_type="twr_radio",
        )

        if not neighbors:
            return None

        stamp_sec = int(world.sim_time_ns // 1_000_000_000)
        stamp_nsec = int(world.sim_time_ns % 1_000_000_000)

        msg = RangeArray()
        msg.header = Header()
        msg.header.stamp.sec = stamp_sec
        msg.header.stamp.nanosec = stamp_nsec
        msg.header.frame_id = f"{agent.agent_id}/radio"

        for other, true_dist in neighbors:
            r = RangeStamped()
            r.header = Header()
            r.header.stamp.sec = stamp_sec
            r.header.stamp.nanosec = stamp_nsec
            r.header.frame_id = f"{agent.agent_id}/radio"
            r.remote_agent_id = other.agent_id
            r.range_m = true_dist + self.gauss(0.0, self._std_m)
            r.range_std_m = self._std_m
            msg.ranges.append(r)

        return msg

    def get_config(self) -> dict[str, Any]:
        base = super().get_config()
        base["topic_suffix"] = self._topic_suffix
        base["max_range_m"] = self._max_range_m
        base["noise"] = {"std_m": self._std_m}
        return base
