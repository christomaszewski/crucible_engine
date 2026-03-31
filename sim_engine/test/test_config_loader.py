"""Tests for sim_engine.config_loader — YAML parsing and scenario management."""

import pytest
import yaml

from sim_engine.agent import Agent, Pose
from sim_engine.config_loader import (
    build_motion,
    build_sensor,
    build_world_from_config,
    load_agent_from_config,
    load_scenario,
    save_scenario,
)
from sim_engine.sensors import SENSOR_REGISTRY
from sim_engine.motion import MOTION_REGISTRY
from sim_engine.world_state import WorldState


MINIMAL_SCENARIO = """
sim:
  sim_dt: 0.01
  speed_multiplier: 1.0
  seed: 42

agents:
  uav_01:
    domain_id: 1
    vehicle_type: uav
    vehicle_class: quadrotor
    initial_pose:
      lat: 38.9072
      lon: -77.0369
      alt: 100.0
      heading: 0.0
    motion:
      type: static
    sensors:
      gps:
        type: navsatfix
        rate_hz: 10.0
        noise:
          horizontal_std_m: 1.5
"""


class TestLoadScenario:
    def test_valid_yaml(self):
        config = load_scenario(MINIMAL_SCENARIO)
        assert "sim" in config
        assert "agents" in config
        assert "uav_01" in config["agents"]

    def test_sim_params(self):
        config = load_scenario(MINIMAL_SCENARIO)
        assert config["sim"]["sim_dt"] == 0.01
        assert config["sim"]["speed_multiplier"] == 1.0
        assert config["sim"]["seed"] == 42

    def test_empty_string_returns_none_or_empty(self):
        config = load_scenario("")
        assert config is None or config == {}

    def test_invalid_yaml(self):
        with pytest.raises(Exception):
            load_scenario("{{invalid yaml: [[[")


class TestBuildSensor:
    def test_navsatfix(self):
        sensor = build_sensor("gps", {"type": "navsatfix", "rate_hz": 5.0})
        assert sensor.rate_hz == 5.0
        assert sensor.sensor_type_name == "navsatfix"

    def test_imu(self):
        sensor = build_sensor("imu0", {"type": "imu", "rate_hz": 100.0})
        assert sensor.rate_hz == 100.0

    def test_altimeter(self):
        sensor = build_sensor("alt", {"type": "altimeter"})
        assert sensor.sensor_type_name == "altimeter"

    def test_twr_radio(self):
        sensor = build_sensor("radio", {"type": "twr_radio", "max_range_m": 1000.0})
        cfg = sensor.get_config()
        assert cfg["max_range_m"] == 1000.0

    def test_unknown_type_raises(self):
        with pytest.raises((KeyError, ValueError)):
            build_sensor("bad", {"type": "nonexistent_sensor"})


class TestBuildMotion:
    def test_static(self):
        motion = build_motion({"type": "static"})
        assert motion.motion_type_name == "static"

    def test_waypoint(self):
        motion = build_motion({
            "type": "waypoint",
            "speed_mps": 5.0,
            "waypoints": [{"lat": 0.0, "lon": 0.0, "alt": 0.0}],
        })
        assert motion.motion_type_name == "waypoint"
        cfg = motion.get_config()
        assert cfg["speed_mps"] == 5.0

    def test_commanded_velocity(self):
        motion = build_motion({"type": "commanded_velocity", "max_speed_mps": 15.0})
        assert motion.motion_type_name == "commanded_velocity"

    def test_unknown_type_raises(self):
        with pytest.raises((KeyError, ValueError)):
            build_motion({"type": "nonexistent_motion"})


class TestLoadAgentFromConfig:
    def test_basic_agent(self):
        cfg = {
            "domain_id": 3,
            "vehicle_type": "usv",
            "vehicle_class": "catamaran",
            "initial_pose": {"lat": 10.0, "lon": 20.0, "alt": 0.0, "heading": 1.5},
            "motion": {"type": "static"},
            "sensors": {
                "gps": {"type": "navsatfix", "rate_hz": 5.0},
            },
        }
        agent = load_agent_from_config("usv_01", cfg)
        assert agent.agent_name == "usv_01"
        assert agent.domain_id == 3
        assert agent.vehicle_type == "usv"
        assert agent.vehicle_class == "catamaran"
        assert agent.pose.latitude == 10.0
        assert agent.pose.heading == 1.5
        assert "gps" in agent.sensors
        assert agent.motion_model is not None

    def test_agent_with_stack_config(self):
        cfg = {
            "initial_pose": {"lat": 0.0, "lon": 0.0, "alt": 0.0},
            "motion": {"type": "static"},
            "sensors": {},
            "stack": {
                "compose_file": "/opt/stacks/agent.yml",
                "env": {"FOO": "bar"},
                "auto_launch": True,
            },
        }
        agent = load_agent_from_config("test_01", cfg)
        assert agent.stack_compose_file == "/opt/stacks/agent.yml"
        assert agent.stack_env == {"FOO": "bar"}
        assert agent.stack_auto_launch is True

    def test_agent_no_sensors(self):
        cfg = {
            "initial_pose": {"lat": 0.0, "lon": 0.0},
            "motion": {"type": "static"},
        }
        agent = load_agent_from_config("bare_01", cfg)
        assert len(agent.sensors) == 0


class TestBuildWorldFromConfig:
    def test_from_minimal_scenario(self):
        config = load_scenario(MINIMAL_SCENARIO)
        world, sim_cfg = build_world_from_config(config)
        assert world.agent_exists("uav_01")
        agent = world.get_agent("uav_01")
        assert agent.vehicle_type == "uav"
        assert "gps" in agent.sensors
        assert sim_cfg["sim_dt"] == 0.01

    def test_multi_agent_scenario(self):
        yaml_str = """
sim:
  sim_dt: 0.01
agents:
  uav_01:
    initial_pose: {lat: 0, lon: 0, alt: 100}
    motion: {type: static}
  uav_02:
    initial_pose: {lat: 1, lon: 1, alt: 200}
    motion: {type: static}
"""
        config = load_scenario(yaml_str)
        world, _ = build_world_from_config(config)
        assert len(world.get_all_agents()) == 2


class TestSaveScenario:
    def test_round_trip(self):
        """Load -> build world -> save -> reload should preserve agents."""
        config = load_scenario(MINIMAL_SCENARIO)
        world, sim_cfg = build_world_from_config(config)
        yaml_out = save_scenario(world, sim_cfg)

        # Reload and verify
        config2 = load_scenario(yaml_out)
        assert "uav_01" in config2["agents"]
        agent_cfg = config2["agents"]["uav_01"]
        assert agent_cfg["vehicle_type"] == "uav"
        assert abs(agent_cfg["initial_pose"]["lat"] - 38.9072) < 0.0001

    def test_round_trip_preserves_sensors(self):
        config = load_scenario(MINIMAL_SCENARIO)
        world, sim_cfg = build_world_from_config(config)
        yaml_out = save_scenario(world, sim_cfg)
        config2 = load_scenario(yaml_out)
        sensors = config2["agents"]["uav_01"].get("sensors", {})
        assert "gps" in sensors
        assert sensors["gps"]["type"] == "navsatfix"

    def test_save_empty_world(self):
        world = WorldState()
        sim_cfg = {"sim_dt": 0.01, "speed_multiplier": 1.0}
        yaml_out = save_scenario(world, sim_cfg)
        config = load_scenario(yaml_out)
        assert len(config.get("agents", {})) == 0
