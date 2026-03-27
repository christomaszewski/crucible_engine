"""Sim engine ROS2 node — main simulation loop and service interface."""

from __future__ import annotations

import json
import logging
from dataclasses import replace
from typing import Any

import rclpy
from geometry_msgs.msg import Quaternion, Twist, Vector3
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import (
    QoSDurabilityPolicy,
    QoSHistoryPolicy,
    QoSProfile,
    QoSReliabilityPolicy,
)
from rosgraph_msgs.msg import Clock
from std_msgs.msg import Header

from crucible_msgs.msg import GroundTruth
from crucible_msgs.srv import (
    AddAgent,
    ConfigureSensor,
    LoadScenario,
    RemoveAgent,
    RemoveSensor,
    SaveScenario,
    SetPose,
    SetSpeed,
    SimControl,
)

from sim_engine.agent import Agent, Pose, Velocity
from sim_engine.config_loader import (
    build_sensor,
    build_motion,
    build_world_from_config,
    load_agent_from_config,
    load_scenario,
    save_scenario,
)
from sim_engine.motion.commanded import CommandedVelocityModel
from sim_engine.plugin_discovery import discover_all_plugins
from sim_engine.scenario_runner import ScenarioRunner
from sim_engine.sensors import QoSPreset, SensorModel, TopicConfig
from sim_engine.world_state import WorldState

logger = logging.getLogger(__name__)


def _make_qos(preset: QoSPreset) -> QoSProfile:
    """Convert a QoSPreset enum to a rclpy QoSProfile."""
    if preset == QoSPreset.RELIABLE:
        return QoSProfile(
            history=QoSHistoryPolicy.KEEP_LAST,
            depth=10,
            reliability=QoSReliabilityPolicy.RELIABLE,
            durability=QoSDurabilityPolicy.VOLATILE,
        )
    # SENSOR_DATA default
    return QoSProfile(
        history=QoSHistoryPolicy.KEEP_LAST,
        depth=5,
        reliability=QoSReliabilityPolicy.BEST_EFFORT,
        durability=QoSDurabilityPolicy.VOLATILE,
    )


class _AgentPublishers:
    """Manages ROS2 publishers for a single agent."""

    def __init__(self) -> None:
        self.sensor_pubs: dict[str, Any] = {}  # sensor_name -> publisher
        self.ground_truth_pub: Any = None
        self.cmd_vel_sub: Any = None


class SimEngineNode(Node):
    """Main simulation engine node.

    Runs the sim loop as a timer callback, manages per-agent publishers,
    and exposes ROS2 services for agent/sensor/scenario management.
    """

    def __init__(self) -> None:
        super().__init__("sim_engine")

        # Discover all built-in and plugin sensor/motion models
        discover_all_plugins()

        # Declare parameters
        self.declare_parameter("sim_dt", 0.01)  # fixed sim step size (seconds)
        self.declare_parameter("speed_multiplier", 1.0)
        self.declare_parameter("seed", 42)
        self.declare_parameter("config_file", "")
        self.declare_parameter("ground_truth_rate_hz", 50.0)

        self._sim_dt: float = (
            self.get_parameter("sim_dt").get_parameter_value().double_value
        )
        self._speed_multiplier: float = (
            self.get_parameter("speed_multiplier")
            .get_parameter_value()
            .double_value
        )
        self._global_seed = (
            self.get_parameter("seed").get_parameter_value().integer_value
        )
        self._gt_rate_hz = (
            self.get_parameter("ground_truth_rate_hz")
            .get_parameter_value()
            .double_value
        )

        # Sim state
        self._world = WorldState()
        self._scenario = ScenarioRunner(self._world)
        self._status = "READY"  # READY, RUNNING, PAUSED, COMPLETE
        self._agent_pubs: dict[str, _AgentPublishers] = {}
        self._gt_accumulator: float = 0.0

        # Initial poses for reset (agent_id -> Pose copy)
        self._initial_poses: dict[str, Pose] = {}

        # Sim config dict (for save/load)
        self._sim_cfg: dict[str, Any] = {
            "sim_dt": self._sim_dt,
            "speed_multiplier": self._speed_multiplier,
            "seed": self._global_seed,
        }

        # Clock publisher
        self._clock_pub = self.create_publisher(Clock, "/clock", 10)

        # Services
        self.create_service(AddAgent, "/sim/add_agent", self._srv_add_agent)
        self.create_service(
            RemoveAgent, "/sim/remove_agent", self._srv_remove_agent
        )
        self.create_service(
            ConfigureSensor, "/sim/configure_sensor", self._srv_configure_sensor
        )
        self.create_service(
            LoadScenario, "/sim/load_scenario", self._srv_load_scenario
        )
        self.create_service(
            SaveScenario, "/sim/save_scenario", self._srv_save_scenario
        )
        self.create_service(
            RemoveSensor, "/sim/remove_sensor", self._srv_remove_sensor
        )
        self.create_service(
            SetPose, "/sim/set_pose", self._srv_set_pose
        )
        self.create_service(
            SimControl, "/sim/sim_control", self._srv_sim_control
        )
        self.create_service(
            SetSpeed, "/sim/set_speed", self._srv_set_speed
        )

        # Sim loop timer — period = sim_dt / speed (or uncapped if speed == 0)
        self._timer = self._create_tick_timer()

        # Load config file if provided (must be after timer creation)
        config_file = (
            self.get_parameter("config_file").get_parameter_value().string_value
        )
        if config_file:
            self._load_config_file(config_file)

        self.get_logger().info(
            f"CRUCIBLE sim engine started: sim_dt={self._sim_dt:.4f}s, speed={self._speed_multiplier:.1f}x"
        )

    # -- Sim loop ------------------------------------------------------------

    def _create_tick_timer(self):
        """Create (or recreate) the sim loop timer based on current speed."""
        if self._speed_multiplier > 0:
            period = self._sim_dt / self._speed_multiplier
        else:
            # Max speed — fire as fast as ROS2 will allow
            period = 1e-6
        return self.create_timer(period, self._tick)

    def _rebuild_timer(self) -> None:
        """Destroy and recreate the tick timer (e.g. after speed change)."""
        self.destroy_timer(self._timer)
        self._timer = self._create_tick_timer()

    def _tick(self) -> None:
        """Main simulation tick — motion, sensors, ground truth, clock."""
        if self._status != "RUNNING":
            return

        self._step_once()

    def _step_once(self) -> None:
        """Advance the simulation by exactly one sim_dt."""
        sim_dt = self._sim_dt

        # Advance sim time
        self._world.sim_time_ns += int(sim_dt * 1e9)

        # Run scenario events
        self._scenario.tick(self._world.sim_time_sec)

        # Update motion models
        for agent in self._world.get_all_agents():
            if agent.motion_model:
                agent.motion_model.step(agent, self._world, sim_dt)

        # Update sensors and publish
        for agent in self._world.get_all_agents():
            pubs = self._agent_pubs.get(agent.agent_id)
            if pubs is None:
                continue

            for sensor_name, sensor in agent.sensors.items():
                pub = pubs.sensor_pubs.get(sensor_name)
                if pub is None:
                    continue
                msg = sensor.update(agent, self._world, sim_dt)
                if msg is not None:
                    pub.publish(msg)

        # Publish ground truth
        self._gt_accumulator += sim_dt
        gt_interval = 1.0 / self._gt_rate_hz if self._gt_rate_hz > 0 else float("inf")
        if self._gt_accumulator >= gt_interval:
            self._gt_accumulator -= gt_interval
            self._publish_ground_truth()

        # Publish clock
        clock_msg = Clock()
        clock_msg.clock.sec = int(self._world.sim_time_ns // 1_000_000_000)
        clock_msg.clock.nanosec = int(self._world.sim_time_ns % 1_000_000_000)
        self._clock_pub.publish(clock_msg)

    def _publish_ground_truth(self) -> None:
        """Publish GroundTruth for all agents."""
        stamp_sec = int(self._world.sim_time_ns // 1_000_000_000)
        stamp_nsec = int(self._world.sim_time_ns % 1_000_000_000)

        for agent in self._world.get_all_agents():
            pubs = self._agent_pubs.get(agent.agent_id)
            if pubs is None or pubs.ground_truth_pub is None:
                continue

            from sim_engine.sensors.imu import euler_to_quaternion

            msg = GroundTruth()
            msg.header = Header()
            msg.header.stamp.sec = stamp_sec
            msg.header.stamp.nanosec = stamp_nsec
            msg.header.frame_id = f"{agent.agent_id}/base_link"
            msg.latitude = agent.pose.latitude
            msg.longitude = agent.pose.longitude
            msg.altitude = agent.pose.altitude
            msg.orientation = euler_to_quaternion(
                agent.pose.roll, agent.pose.pitch, agent.pose.heading
            )
            msg.linear_velocity = Vector3(
                x=agent.velocity.vx,
                y=agent.velocity.vy,
                z=agent.velocity.vz,
            )
            msg.angular_velocity = Vector3(
                x=agent.velocity.wx,
                y=agent.velocity.wy,
                z=agent.velocity.wz,
            )
            pubs.ground_truth_pub.publish(msg)

    # -- Agent lifecycle -----------------------------------------------------

    def _register_agent(self, agent: Agent) -> None:
        """Create publishers and subscribers for an agent."""
        pubs = _AgentPublishers()

        # Sensor publishers
        for sensor_name, sensor in agent.sensors.items():
            tc = sensor.get_topic_config()
            topic = f"/{agent.agent_id}/{tc.suffix}"
            pub = self.create_publisher(tc.msg_type, topic, _make_qos(tc.qos))
            pubs.sensor_pubs[sensor_name] = pub
            self.get_logger().info(f"Publishing: {topic} [{tc.msg_type.__name__}]")

        # Ground truth publisher
        gt_topic = f"/{agent.agent_id}/sim/ground_truth"
        pubs.ground_truth_pub = self.create_publisher(GroundTruth, gt_topic, 10)
        self.get_logger().info(f"Publishing ground truth: {gt_topic}")

        # Command velocity subscriber (if commanded motion)
        if isinstance(agent.motion_model, CommandedVelocityModel):
            cmd_topic = f"/{agent.agent_id}/{agent.motion_model.topic_suffix}"
            pubs.cmd_vel_sub = self.create_subscription(
                Twist,
                cmd_topic,
                agent.motion_model.on_command,
                10,
            )
            self.get_logger().info(f"Subscribing cmd_vel: {cmd_topic}")

        self._agent_pubs[agent.agent_id] = pubs

    def _unregister_agent(self, agent_id: str) -> None:
        """Destroy publishers and subscribers for an agent."""
        pubs = self._agent_pubs.pop(agent_id, None)
        if pubs is None:
            return

        for pub in pubs.sensor_pubs.values():
            self.destroy_publisher(pub)
        if pubs.ground_truth_pub:
            self.destroy_publisher(pubs.ground_truth_pub)
        if pubs.cmd_vel_sub:
            self.destroy_subscription(pubs.cmd_vel_sub)

    # -- Service handlers ----------------------------------------------------

    def _srv_add_agent(
        self, request: AddAgent.Request, response: AddAgent.Response
    ) -> AddAgent.Response:
        try:
            if self._world.agent_exists(request.agent_id):
                response.success = False
                response.message = f"Agent '{request.agent_id}' already exists"
                return response

            agent = Agent(
                agent_id=request.agent_id,
                pose=Pose(
                    latitude=request.latitude,
                    longitude=request.longitude,
                    altitude=request.altitude,
                    heading=request.heading,
                ),
                velocity=Velocity(),
                domain_id=request.domain_id,
                vehicle_type=request.vehicle_type,
                vehicle_class=request.vehicle_class,
            )

            # Default to static motion
            from sim_engine.motion.static import StaticMotionModel

            agent.motion_model = StaticMotionModel()
            agent.motion_model.configure({})

            self._world.add_agent(agent)
            self._register_agent(agent)
            self._initial_poses[request.agent_id] = replace(agent.pose)

            response.success = True
            response.message = f"Agent '{request.agent_id}' added"
        except Exception as e:
            response.success = False
            response.message = str(e)
        return response

    def _srv_remove_agent(
        self, request: RemoveAgent.Request, response: RemoveAgent.Response
    ) -> RemoveAgent.Response:
        try:
            self._unregister_agent(request.agent_id)
            self._world.remove_agent(request.agent_id)
            self._initial_poses.pop(request.agent_id, None)
            response.success = True
            response.message = f"Agent '{request.agent_id}' removed"
        except Exception as e:
            response.success = False
            response.message = str(e)
        return response

    def _srv_configure_sensor(
        self,
        request: ConfigureSensor.Request,
        response: ConfigureSensor.Response,
    ) -> ConfigureSensor.Response:
        try:
            agent = self._world.get_agent(request.agent_id)
            sensor_cfg = json.loads(request.config_json)
            sensor_name = request.sensor_name

            # If sensor exists, destroy its publisher first
            pubs = self._agent_pubs.get(request.agent_id)
            if pubs and sensor_name in pubs.sensor_pubs:
                self.destroy_publisher(pubs.sensor_pubs.pop(sensor_name))

            # Build new sensor
            sensor = build_sensor(sensor_name, sensor_cfg)
            agent.sensors[sensor_name] = sensor

            # Create new publisher
            if pubs:
                tc = sensor.get_topic_config()
                topic = f"/{agent.agent_id}/{tc.suffix}"
                pub = self.create_publisher(tc.msg_type, topic, _make_qos(tc.qos))
                pubs.sensor_pubs[sensor_name] = pub

            response.success = True
            response.message = f"Sensor '{sensor_name}' configured on '{request.agent_id}'"
        except Exception as e:
            response.success = False
            response.message = str(e)
        return response

    def _srv_remove_sensor(
        self,
        request: RemoveSensor.Request,
        response: RemoveSensor.Response,
    ) -> RemoveSensor.Response:
        try:
            agent = self._world.get_agent(request.agent_id)
            sensor_name = request.sensor_name

            if sensor_name not in agent.sensors:
                response.success = False
                response.message = f"Sensor '{sensor_name}' not found on '{request.agent_id}'"
                return response

            # Destroy publisher
            pubs = self._agent_pubs.get(request.agent_id)
            if pubs and sensor_name in pubs.sensor_pubs:
                self.destroy_publisher(pubs.sensor_pubs.pop(sensor_name))

            del agent.sensors[sensor_name]

            response.success = True
            response.message = f"Sensor '{sensor_name}' removed from '{request.agent_id}'"
        except Exception as e:
            response.success = False
            response.message = str(e)
        return response

    def _srv_set_pose(
        self,
        request: SetPose.Request,
        response: SetPose.Response,
    ) -> SetPose.Response:
        try:
            agent = self._world.get_agent(request.agent_id)
            agent.pose.latitude = request.latitude
            agent.pose.longitude = request.longitude
            agent.pose.altitude = request.altitude
            agent.pose.heading = request.heading

            # If sim hasn't started yet, this is an initial condition change
            if self._world.sim_time_ns == 0:
                self._initial_poses[request.agent_id] = replace(agent.pose)

            response.success = True
            response.message = f"Pose updated for '{request.agent_id}'"
        except Exception as e:
            response.success = False
            response.message = str(e)
        return response

    def _srv_load_scenario(
        self,
        request: LoadScenario.Request,
        response: LoadScenario.Response,
    ) -> LoadScenario.Response:
        try:
            config = load_scenario(request.config_yaml)

            # Clear existing agents
            for agent_id in list(self._agent_pubs.keys()):
                self._unregister_agent(agent_id)
            # Rebuild world
            self._world = WorldState()
            world, sim_cfg = build_world_from_config(config)
            self._world = world
            self._sim_cfg.update(sim_cfg)

            # Update timing params if changed
            new_dt = sim_cfg.get("sim_dt", self._sim_dt)
            new_speed = sim_cfg.get("speed_multiplier", self._speed_multiplier)
            needs_rebuild = (new_dt != self._sim_dt or new_speed != self._speed_multiplier)
            self._sim_dt = new_dt
            self._speed_multiplier = new_speed
            if needs_rebuild:
                self._rebuild_timer()

            # Register all agents and store initial poses
            self._initial_poses.clear()
            for agent in self._world.get_all_agents():
                self._register_agent(agent)
                self._initial_poses[agent.agent_id] = replace(agent.pose)

            # Load scenario events
            events = config.get("scenario", {}).get("events", [])
            self._scenario = ScenarioRunner(self._world)
            self._scenario.load_events(events)

            # Ready state after load so user can inspect before running
            self._status = "READY"

            response.success = True
            response.message = f"Loaded scenario with {len(self._world.get_all_agents())} agents"
        except Exception as e:
            response.success = False
            response.message = str(e)
            logger.exception("Failed to load scenario")
        return response

    def _srv_save_scenario(
        self,
        request: SaveScenario.Request,
        response: SaveScenario.Response,
    ) -> SaveScenario.Response:
        try:
            self._sim_cfg["status"] = self._status
            yaml_str = save_scenario(self._world, self._sim_cfg)
            response.config_yaml = yaml_str
            response.success = True
            response.message = "Scenario saved"

            if request.file_path:
                with open(request.file_path, "w") as f:
                    f.write(yaml_str)
                response.message = f"Scenario saved to {request.file_path}"
        except Exception as e:
            response.success = False
            response.message = str(e)
        return response

    def _srv_sim_control(
        self,
        request: SimControl.Request,
        response: SimControl.Response,
    ) -> SimControl.Response:
        action = request.action.lower()
        try:
            if action == "resume":
                self._status = "RUNNING"
                response.success = True
                response.message = "Simulation running"
            elif action == "pause":
                self._status = "PAUSED"
                response.success = True
                response.message = "Simulation paused"
            elif action == "step":
                if self._status == "RUNNING":
                    response.success = False
                    response.message = "Cannot step while running — pause first"
                else:
                    self._step_once()
                    self._status = "PAUSED"  # stepping means we've left READY
                    response.success = True
                    response.message = f"Stepped {self._sim_dt:.4f}s"
            elif action == "reset":
                self._status = "READY"
                self._world.sim_time_ns = 0
                self._gt_accumulator = 0.0
                # Restore initial poses and zero velocities
                for agent in self._world.get_all_agents():
                    initial = self._initial_poses.get(agent.agent_id)
                    if initial:
                        agent.pose = replace(initial)
                    agent.velocity = Velocity()
                response.success = True
                response.message = "Simulation reset to initial conditions"
            elif action.startswith("set_dt:"):
                if self._status != "READY":
                    response.success = False
                    response.message = "Can only change dt in READY state"
                else:
                    new_dt = float(action.split(":")[1])
                    if new_dt <= 0:
                        response.success = False
                        response.message = "sim_dt must be > 0"
                    else:
                        self._sim_dt = new_dt
                        self._sim_cfg["sim_dt"] = new_dt
                        self._rebuild_timer()
                        response.success = True
                        response.message = f"sim_dt set to {new_dt:.4f}s"
            else:
                response.success = False
                response.message = f"Unknown action: {action}"
        except Exception as e:
            response.success = False
            response.message = str(e)
        response.status = self._status
        return response

    def _srv_set_speed(
        self,
        request: SetSpeed.Request,
        response: SetSpeed.Response,
    ) -> SetSpeed.Response:
        try:
            multiplier = request.speed_multiplier
            if multiplier < 0:
                response.success = False
                response.message = "Speed multiplier must be >= 0"
                response.effective_multiplier = self._speed_multiplier
                return response

            self._speed_multiplier = multiplier
            self._sim_cfg["speed_multiplier"] = multiplier
            self._rebuild_timer()

            response.success = True
            if multiplier == 0:
                response.message = "Speed set to max (uncapped)"
            else:
                response.message = f"Speed set to {multiplier:.1f}x"
            response.effective_multiplier = multiplier
        except Exception as e:
            response.success = False
            response.message = str(e)
            response.effective_multiplier = self._speed_multiplier
        return response

    # -- Config loading ------------------------------------------------------

    def _load_config_file(self, path: str) -> None:
        """Load scenario from a YAML file at startup."""
        try:
            with open(path) as f:
                config = load_scenario(f.read())

            world, sim_cfg = build_world_from_config(config)
            self._world = world
            self._sim_cfg.update(sim_cfg)

            self._sim_dt = sim_cfg.get("sim_dt", self._sim_dt)
            self._speed_multiplier = sim_cfg.get(
                "speed_multiplier", self._speed_multiplier
            )
            self._rebuild_timer()

            self._initial_poses.clear()
            for agent in self._world.get_all_agents():
                self._register_agent(agent)
                self._initial_poses[agent.agent_id] = replace(agent.pose)

            events = config.get("scenario", {}).get("events", [])
            self._scenario = ScenarioRunner(self._world)
            self._scenario.load_events(events)

            self.get_logger().info(f"Loaded config: {path}")
        except Exception as e:
            self.get_logger().error(f"Failed to load config: {path}\n{e}")


def main(args=None):
    rclpy.init(args=args)
    node = SimEngineNode()

    executor = MultiThreadedExecutor(num_threads=4)
    executor.add_node(node)

    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
