"""YAML scenario configuration loader and saver."""

from __future__ import annotations

import logging
from typing import Any

import yaml

from sim_engine.agent import Agent, Pose, Velocity
from sim_engine.motion import MOTION_REGISTRY, MotionModel
from sim_engine.sensors import SENSOR_REGISTRY, SensorModel
from sim_engine.world_state import WorldState

logger = logging.getLogger(__name__)


def build_sensor(sensor_name: str, sensor_cfg: dict[str, Any]) -> SensorModel:
    """Construct and configure a sensor model from config."""
    sensor_type = sensor_cfg.get("type", sensor_name)
    cls = SENSOR_REGISTRY.get(sensor_type)
    if cls is None:
        raise ValueError(
            f"Unknown sensor type '{sensor_type}'. "
            f"Available: {list(SENSOR_REGISTRY.keys())}"
        )
    sensor = cls()
    sensor.configure(sensor_cfg)
    return sensor


def build_motion(motion_cfg: dict[str, Any]) -> MotionModel:
    """Construct and configure a motion model from config."""
    motion_type = motion_cfg.get("type", "static")
    cls = MOTION_REGISTRY.get(motion_type)
    if cls is None:
        raise ValueError(
            f"Unknown motion type '{motion_type}'. "
            f"Available: {list(MOTION_REGISTRY.keys())}"
        )
    model = cls()
    model.configure(motion_cfg)
    return model


def load_agent_from_config(agent_name: str, agent_cfg: dict[str, Any]) -> Agent:
    """Build an Agent instance from a config dict."""
    pose_cfg = agent_cfg.get("initial_pose", {})
    pose = Pose(
        latitude=pose_cfg.get("lat", 0.0),
        longitude=pose_cfg.get("lon", 0.0),
        altitude=pose_cfg.get("alt", 0.0),
        heading=pose_cfg.get("heading", 0.0),
    )

    agent = Agent(
        agent_name=agent_name,
        pose=pose,
        velocity=Velocity(),
        domain_id=agent_cfg.get("domain_id", 0),
        vehicle_type=agent_cfg.get("vehicle_type", ""),
        vehicle_class=agent_cfg.get("vehicle_class", ""),
        pose_estimate_topic=agent_cfg.get("pose_estimate_topic"),
    )

    # Motion model
    motion_cfg = agent_cfg.get("motion", {"type": "static"})
    agent.motion_model = build_motion(motion_cfg)

    # Sensors
    for sensor_name, sensor_cfg in agent_cfg.get("sensors", {}).items():
        sensor = build_sensor(sensor_name, sensor_cfg)
        agent.sensors[sensor_name] = sensor

    # Stack config
    stack_cfg = agent_cfg.get("stack", {})
    agent.stack_compose_file = stack_cfg.get("compose_file")
    agent.stack_env = stack_cfg.get("env", {})
    agent.stack_auto_launch = stack_cfg.get("auto_launch", False)

    return agent


def load_scenario(yaml_str: str) -> dict[str, Any]:
    """Parse a YAML scenario string and return the raw config dict."""
    return yaml.safe_load(yaml_str)


def build_world_from_config(config: dict[str, Any]) -> tuple[WorldState, dict]:
    """Construct a WorldState populated with agents from a config dict.

    Returns:
        Tuple of (world_state, sim_config) where sim_config contains
        top-level sim parameters (sim_dt, speed_multiplier, etc.)
    """
    world = WorldState()
    sim_cfg = config.get("sim", {})

    # Terrain
    dem_path = sim_cfg.get("terrain", {}).get("dem_path")
    if dem_path:
        from sim_engine.terrain import TerrainModel

        world.terrain = TerrainModel(dem_path)

    # Agents
    for agent_name, agent_cfg in config.get("agents", {}).items():
        agent = load_agent_from_config(agent_name, agent_cfg)
        world.add_agent(agent)

    return world, sim_cfg


def save_scenario(world: WorldState, sim_cfg: dict[str, Any]) -> str:
    """Serialize the current world state and sim config to YAML."""
    config: dict[str, Any] = {
        "sim": {
            "sim_dt": sim_cfg.get("sim_dt", 0.01),
            "speed_multiplier": sim_cfg.get("speed_multiplier", 1.0),
            "seed": sim_cfg.get("seed", 42),
            "sim_time_s": world.sim_time_sec,
            "status": sim_cfg.get("status", "READY"),
        },
        "agents": {},
    }

    # Terrain
    if world.terrain and world.terrain.available:
        config["sim"]["terrain"] = {"dem_path": sim_cfg.get("terrain", {}).get("dem_path", "")}

    for agent in world.get_all_agents():
        agent_cfg: dict[str, Any] = {
            "domain_id": agent.domain_id,
            "vehicle_type": agent.vehicle_type,
            "vehicle_class": agent.vehicle_class,
            "initial_pose": {
                "lat": agent.pose.latitude,
                "lon": agent.pose.longitude,
                "alt": agent.pose.altitude,
                "heading": agent.pose.heading,
            },
        }

        # Motion
        if agent.motion_model:
            agent_cfg["motion"] = agent.motion_model.get_config()

        # Sensors
        sensors_cfg: dict[str, Any] = {}
        for sname, sensor in agent.sensors.items():
            sensors_cfg[sname] = sensor.get_config()
        if sensors_cfg:
            agent_cfg["sensors"] = sensors_cfg

        # Pose estimate
        if agent.pose_estimate_topic:
            agent_cfg["pose_estimate_topic"] = agent.pose_estimate_topic

        # Stack
        if agent.stack_compose_file:
            agent_cfg["stack"] = {
                "compose_file": agent.stack_compose_file,
                "auto_launch": agent.stack_auto_launch,
                "env": agent.stack_env,
            }

        config["agents"][agent.agent_name] = agent_cfg

    return yaml.dump(config, default_flow_style=False, sort_keys=False)
