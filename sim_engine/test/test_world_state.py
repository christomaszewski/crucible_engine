"""Tests for sim_engine.world_state — WorldState agent registry and queries."""

import threading
import pytest

from sim_engine.agent import Agent, Pose
from sim_engine.world_state import WorldState


class TestWorldStateBasic:
    def test_empty(self, world):
        assert world.get_all_agents() == []
        assert not world.agent_exists("nobody")

    def test_add_agent(self, world, agent_basic):
        world.add_agent(agent_basic)
        assert world.agent_exists("uav_01")
        assert world.get_agent("uav_01") is agent_basic

    def test_add_duplicate_raises(self, world, agent_basic):
        world.add_agent(agent_basic)
        with pytest.raises(ValueError):
            world.add_agent(agent_basic)

    def test_remove_agent(self, world, agent_basic):
        world.add_agent(agent_basic)
        removed = world.remove_agent("uav_01")
        assert removed is agent_basic
        assert not world.agent_exists("uav_01")

    def test_remove_nonexistent_raises(self, world):
        with pytest.raises(KeyError):
            world.remove_agent("nobody")

    def test_get_nonexistent_raises(self, world):
        with pytest.raises(KeyError):
            world.get_agent("nobody")

    def test_get_all_agents(self, populated_world):
        agents = populated_world.get_all_agents()
        names = {a.agent_name for a in agents}
        assert names == {"uav_01", "uav_02"}


class TestWorldStateSimTime:
    def test_default_time(self, world):
        assert world.sim_time_ns == 0
        assert world.sim_time_sec == 0.0

    def test_set_time(self, world):
        world.sim_time_ns = 1_000_000_000  # 1 second
        assert world.sim_time_ns == 1_000_000_000
        assert world.sim_time_sec == pytest.approx(1.0)

    def test_set_time_fractional(self, world):
        world.sim_time_ns = 1_500_000_000  # 1.5 seconds
        assert world.sim_time_sec == pytest.approx(1.5)


class TestWorldStateSpatialQueries:
    def test_agents_within_range(self, populated_world):
        """uav_01 and uav_02 are ~111m apart."""
        results = populated_world.agents_within_range("uav_01", max_range_m=200.0)
        assert len(results) == 1
        agent, dist = results[0]
        assert agent.agent_name == "uav_02"
        assert 100 < dist < 120

    def test_agents_out_of_range(self, populated_world):
        results = populated_world.agents_within_range("uav_01", max_range_m=10.0)
        assert len(results) == 0

    def test_agents_within_range_excludes_self(self, populated_world):
        """Should not include the querying agent itself."""
        results = populated_world.agents_within_range("uav_01", max_range_m=999999.0)
        names = [a.agent_name for a, _ in results]
        assert "uav_01" not in names

    def test_agents_within_range_nonexistent_agent(self, populated_world):
        with pytest.raises(KeyError):
            populated_world.agents_within_range("nobody", max_range_m=100.0)


class TestWorldStateSnapshot:
    def test_snapshot_structure(self, populated_world):
        snap = populated_world.snapshot()
        assert "agents" in snap
        assert "sim_time_s" in snap
        assert len(snap["agents"]) == 2

    def test_snapshot_agent_fields(self, populated_world):
        snap = populated_world.snapshot()
        a = snap["agents"]["uav_01"]
        assert a["domain_id"] == 1
        assert "lat" in a
        assert "lon" in a
        assert "heading" in a
        assert "sensors" in a


class TestWorldStateTerrain:
    def test_elevation_without_model(self, world):
        """No terrain model loaded — should return None."""
        assert world.get_terrain_elevation(0.0, 0.0) is None

    def test_terrain_property_default(self, world):
        assert world.terrain is None


class TestWorldStateThreadSafety:
    def test_concurrent_add_remove(self):
        """Verify no crashes under concurrent access."""
        world = WorldState()
        errors = []

        def add_agents(start, count):
            try:
                for i in range(start, start + count):
                    world.add_agent(Agent(agent_name=f"agent_{i}"))
            except Exception as e:
                errors.append(e)

        def remove_agents(start, count):
            try:
                for i in range(start, start + count):
                    try:
                        world.remove_agent(f"agent_{i}")
                    except KeyError:
                        pass  # expected race
            except Exception as e:
                errors.append(e)

        threads = []
        for batch in range(4):
            t = threading.Thread(target=add_agents, args=(batch * 25, 25))
            threads.append(t)
        for batch in range(4):
            t = threading.Thread(target=remove_agents, args=(batch * 25, 25))
            threads.append(t)

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)

        assert not errors, f"Errors during concurrent access: {errors}"
