"""Plugin discovery for sensor and motion model extensions."""

from __future__ import annotations

import logging

from sim_engine.motion import discover_motion_plugins
from sim_engine.sensors import discover_sensor_plugins

logger = logging.getLogger(__name__)


def discover_all_plugins() -> None:
    """Load all built-in models and discover external plugins via entry points.

    Built-in models are loaded by importing their modules (which triggers
    the @register_sensor / @register_motion decorators). External plugins
    are discovered via Python entry points.
    """
    # Import built-in sensor models to trigger registration
    import sim_engine.sensors.navsatfix  # noqa: F401
    import sim_engine.sensors.imu  # noqa: F401
    import sim_engine.sensors.altimeter  # noqa: F401
    import sim_engine.sensors.twr_radio  # noqa: F401

    # Import built-in motion models
    import sim_engine.motion.static  # noqa: F401
    import sim_engine.motion.waypoint  # noqa: F401
    import sim_engine.motion.commanded  # noqa: F401

    # Discover external plugins
    discover_sensor_plugins()
    discover_motion_plugins()

    from sim_engine.sensors import SENSOR_REGISTRY
    from sim_engine.motion import MOTION_REGISTRY

    logger.info("Sensor models: %s", list(SENSOR_REGISTRY.keys()))
    logger.info("Motion models: %s", list(MOTION_REGISTRY.keys()))
