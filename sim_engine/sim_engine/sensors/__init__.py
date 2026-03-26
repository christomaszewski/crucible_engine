"""Sensor model base class, plugin registry, and topic configuration."""

from __future__ import annotations

import random
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum, auto
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sim_engine.agent import Agent
    from sim_engine.world_state import WorldState

# ---------------------------------------------------------------------------
# Plugin registry
# ---------------------------------------------------------------------------

SENSOR_REGISTRY: dict[str, type[SensorModel]] = {}


def register_sensor(name: str):
    """Decorator to register a sensor model class in the global registry."""

    def decorator(cls: type[SensorModel]) -> type[SensorModel]:
        if name in SENSOR_REGISTRY:
            raise ValueError(f"Sensor '{name}' already registered")
        SENSOR_REGISTRY[name] = cls
        cls.sensor_type_name = name
        return cls

    return decorator


def discover_sensor_plugins() -> None:
    """Discover and load sensor model plugins via entry points."""
    try:
        from importlib.metadata import entry_points

        eps = entry_points(group="sim_engine.sensors")
        for ep in eps:
            cls = ep.load()
            if ep.name not in SENSOR_REGISTRY:
                SENSOR_REGISTRY[ep.name] = cls
    except Exception:
        pass  # No plugins found or importlib issue — not fatal


# ---------------------------------------------------------------------------
# QoS presets
# ---------------------------------------------------------------------------


class QoSPreset(Enum):
    SENSOR_DATA = auto()  # best-effort, volatile, small depth
    RELIABLE = auto()  # reliable, volatile


# ---------------------------------------------------------------------------
# Topic config
# ---------------------------------------------------------------------------


@dataclass
class TopicConfig:
    """Describes the ROS2 topic a sensor publishes on."""

    suffix: str  # e.g. "gps/fix" → /<agent_id>/gps/fix
    msg_type: type  # the ROS2 message class
    qos: QoSPreset = QoSPreset.SENSOR_DATA


# ---------------------------------------------------------------------------
# Sensor model ABC
# ---------------------------------------------------------------------------


class SensorModel(ABC):
    """Abstract base for all sensor simulation models.

    Each concrete model knows how to:
      1. Configure itself from a parameter dict
      2. Describe its output topic
      3. Produce a ROS2 message each update cycle (or None to skip)
    """

    sensor_type_name: str = ""

    def __init__(self) -> None:
        self._rng: random.Random = random.Random()
        self._rate_hz: float = 1.0
        self._accumulator: float = 0.0

    @property
    def rate_hz(self) -> float:
        return self._rate_hz

    def set_seed(self, seed: int) -> None:
        """Set the per-sensor RNG seed for reproducible noise."""
        self._rng = random.Random(seed)

    def gauss(self, mu: float = 0.0, sigma: float = 1.0) -> float:
        """Draw from the sensor's private RNG."""
        return self._rng.gauss(mu, sigma)

    @abstractmethod
    def configure(self, params: dict[str, Any]) -> None:
        """Load sensor parameters from config dict."""
        ...

    @abstractmethod
    def get_topic_config(self) -> TopicConfig:
        """Return the topic name suffix, message type, and QoS preset."""
        ...

    @abstractmethod
    def update(
        self,
        agent: Agent,
        world: WorldState,
        dt: float,
    ) -> Any | None:
        """Produce a ROS2 message for this tick, or None to skip.

        The sim loop calls this at the sim tick rate. The sensor should
        use its internal accumulator to gate output at its own rate.
        """
        ...

    def should_publish(self, dt: float) -> bool:
        """Rate-limiting helper. Call at the top of update()."""
        self._accumulator += dt
        interval = 1.0 / self._rate_hz if self._rate_hz > 0 else float("inf")
        if self._accumulator >= interval:
            self._accumulator -= interval
            return True
        return False

    def get_config(self) -> dict[str, Any]:
        """Return current config as a serializable dict for save/export.

        Subclasses should override to include their specific parameters.
        """
        return {
            "type": self.sensor_type_name,
            "rate_hz": self._rate_hz,
        }
