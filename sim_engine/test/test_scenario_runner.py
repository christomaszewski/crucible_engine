"""Tests for sim_engine.scenario_runner — timed event execution."""

import pytest

from sim_engine.agent import Agent, Pose
from sim_engine.scenario_runner import ScenarioEvent, ScenarioRunner
from sim_engine.sensors.navsatfix import NavSatFixModel
from sim_engine.world_state import WorldState


@pytest.fixture
def runner_world():
    """World with one agent that has a GPS sensor."""
    world = WorldState()
    agent = Agent(agent_name="uav_01", pose=Pose(latitude=10.0, longitude=20.0))
    gps = NavSatFixModel()
    gps.configure({"rate_hz": 10.0})
    agent.sensors["gps"] = gps
    world.add_agent(agent)
    return world


@pytest.fixture
def runner(runner_world):
    return ScenarioRunner(runner_world)


class TestScenarioEvent:
    def test_dataclass_defaults(self):
        e = ScenarioEvent(time_s=5.0, action="disable_sensor")
        assert e.time_s == 5.0
        assert e.action == "disable_sensor"
        assert e.params == {}
        assert e.fired is False


class TestScenarioRunnerLoad:
    def test_load_events(self, runner):
        events = [
            {"time_s": 1.0, "action": "disable_sensor", "agent_name": "uav_01", "sensor": "gps"},
            {"time_s": 5.0, "action": "set_pose", "agent_name": "uav_01", "lat": 0.0, "lon": 0.0},
        ]
        runner.load_events(events)
        cfg = runner.get_events_config()
        assert len(cfg) == 2
        assert cfg[0]["time_s"] == 1.0
        assert cfg[1]["time_s"] == 5.0

    def test_load_empty(self, runner):
        runner.load_events([])
        assert len(runner.get_events_config()) == 0


class TestScenarioRunnerTick:
    def test_fires_at_correct_time(self, runner):
        runner.load_events([
            {"time_s": 2.0, "action": "disable_sensor", "agent_name": "uav_01", "sensor": "gps"},
        ])
        # Before event time — nothing fires
        fired = runner.tick(1.0)
        assert len(fired) == 0

        # At/past event time — fires
        fired = runner.tick(2.5)
        assert len(fired) == 1
        assert fired[0].action == "disable_sensor"

    def test_fires_only_once(self, runner):
        runner.load_events([
            {"time_s": 1.0, "action": "disable_sensor", "agent_name": "uav_01", "sensor": "gps"},
        ])
        fired1 = runner.tick(2.0)
        assert len(fired1) == 1
        fired2 = runner.tick(3.0)
        assert len(fired2) == 0

    def test_multiple_events_ordering(self, runner):
        runner.load_events([
            {"time_s": 3.0, "action": "set_pose", "agent_name": "uav_01", "lat": 0, "lon": 0},
            {"time_s": 1.0, "action": "disable_sensor", "agent_name": "uav_01", "sensor": "gps"},
        ])
        # Tick past both
        fired = runner.tick(5.0)
        assert len(fired) == 2
        # Should fire in time order
        assert fired[0].time_s <= fired[1].time_s


class TestScenarioRunnerReset:
    def test_reset_allows_refire(self, runner):
        runner.load_events([
            {"time_s": 1.0, "action": "disable_sensor", "agent_name": "uav_01", "sensor": "gps"},
        ])
        runner.tick(2.0)
        runner.reset()
        fired = runner.tick(2.0)
        assert len(fired) == 1


class TestScenarioRunnerHandlers:
    def test_disable_sensor(self, runner, runner_world):
        runner.load_events([
            {"time_s": 0.0, "action": "disable_sensor", "agent": "uav_01", "sensor": "gps"},
        ])
        agent = runner_world.get_agent("uav_01")
        assert "gps" in agent.sensors
        runner.tick(1.0)
        # Sensor should be removed
        assert "gps" not in agent.sensors

    def test_set_pose(self, runner, runner_world):
        runner.load_events([
            {"time_s": 0.0, "action": "set_pose", "agent": "uav_01",
             "lat": 55.0, "lon": 66.0, "alt": 999.0, "heading": 1.0},
        ])
        runner.tick(1.0)
        agent = runner_world.get_agent("uav_01")
        assert agent.pose.latitude == pytest.approx(55.0)
        assert agent.pose.longitude == pytest.approx(66.0)
        assert agent.pose.altitude == pytest.approx(999.0)

    def test_handler_nonexistent_agent(self, runner):
        """Events targeting missing agents should not crash."""
        runner.load_events([
            {"time_s": 0.0, "action": "disable_sensor", "agent": "nobody", "sensor": "gps"},
        ])
        # Should not raise
        runner.tick(1.0)
