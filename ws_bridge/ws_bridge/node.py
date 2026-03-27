"""WebSocket bridge node — translates between the frontend and ROS2 services."""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from typing import Any

import rclpy
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node

from rosgraph_msgs.msg import Clock
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

logger = logging.getLogger(__name__)

WS_PORT = 9090


class WsBridgeNode(Node):
    """ROS2 node that bridges WebSocket commands to sim engine services."""

    def __init__(self) -> None:
        super().__init__("ws_bridge")

        # Service clients
        self._cli_add = self.create_client(AddAgent, "/sim/add_agent")
        self._cli_remove = self.create_client(RemoveAgent, "/sim/remove_agent")
        self._cli_configure = self.create_client(
            ConfigureSensor, "/sim/configure_sensor"
        )
        self._cli_load = self.create_client(LoadScenario, "/sim/load_scenario")
        self._cli_save = self.create_client(SaveScenario, "/sim/save_scenario")
        self._cli_remove_sensor = self.create_client(RemoveSensor, "/sim/remove_sensor")
        self._cli_set_pose = self.create_client(SetPose, "/sim/set_pose")
        self._cli_sim_control = self.create_client(SimControl, "/sim/sim_control")
        self._cli_set_speed = self.create_client(SetSpeed, "/sim/set_speed")

        # Ground truth subscribers (created per agent)
        self._gt_subs: dict[str, Any] = {}
        self._pose_est_subs: dict[str, Any] = {}

        # Connected WebSocket clients
        self._ws_clients: set = set()
        self._ws_lock = threading.Lock()

        # Latest state for new connections
        self._latest_state: dict[str, Any] = {}

        # Ground truth cache for broadcasting
        self._gt_cache: dict[str, dict] = {}

        # Monotonic version counter (resets to 0 on restart)
        self._state_version: int = 0

        # Subscribe to /clock for sim time
        self._clock_sub = self.create_subscription(
            Clock, "/clock", self._on_clock, 10
        )

        # Periodically scan for ground truth topics to auto-subscribe
        self._discovery_timer = self.create_timer(2.0, self._discover_agents)

        self.get_logger().info("WS Bridge node initialized")

    # -- WebSocket management ------------------------------------------------

    def register_ws(self, ws) -> None:
        with self._ws_lock:
            self._ws_clients.add(ws)

    def unregister_ws(self, ws) -> None:
        with self._ws_lock:
            self._ws_clients.discard(ws)

    async def broadcast(self, message: dict) -> None:
        """Send a message to all connected WebSocket clients."""
        data = json.dumps(message)
        with self._ws_lock:
            clients = list(self._ws_clients)
        for ws in clients:
            try:
                await ws.send(data)
            except Exception:
                self.unregister_ws(ws)

    def broadcast_sync(self, message: dict) -> None:
        """Thread-safe broadcast from ROS2 callbacks."""
        data = json.dumps(message)
        with self._ws_lock:
            clients = list(self._ws_clients)
        for ws in clients:
            try:
                asyncio.run_coroutine_threadsafe(ws.send(data), self._loop)
            except Exception:
                self.unregister_ws(ws)

    def set_event_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    # -- Command handling ----------------------------------------------------

    async def handle_command(self, ws, data: dict) -> None:
        """Route an incoming WebSocket command to the appropriate handler."""
        cmd = data.get("cmd")
        handler = getattr(self, f"_cmd_{cmd}", None)
        if handler is None:
            await ws.send(
                json.dumps({"type": "error", "message": f"Unknown command: {cmd}"})
            )
            return
        try:
            await handler(ws, data)
        except Exception as e:
            logger.exception("Error handling command: %s", cmd)
            await ws.send(
                json.dumps({"type": "error", "message": str(e)})
            )

    async def _cmd_add_agent(self, ws, data: dict) -> None:
        req = AddAgent.Request()
        req.agent_id = data["agent_id"]
        req.latitude = float(data.get("lat", 0.0))
        req.longitude = float(data.get("lon", 0.0))
        req.altitude = float(data.get("alt", 0.0))
        req.heading = float(data.get("heading", 0.0))
        req.domain_id = int(data.get("domain_id", 0))
        req.vehicle_type = data.get("vehicle_type", "")
        req.vehicle_class = data.get("vehicle_class", "")

        future = self._cli_add.call_async(req)
        result = await self._await_future(future)

        # Subscribe to ground truth for this agent
        self._subscribe_ground_truth(data["agent_id"])

        self._state_version += 1
        await self.broadcast({
            "type": "info",
            "message": result.message,
            "success": result.success,
            "state_version": self._state_version,
        })

    async def _cmd_remove_agent(self, ws, data: dict) -> None:
        req = RemoveAgent.Request()
        req.agent_id = data["agent_id"]

        future = self._cli_remove.call_async(req)
        result = await self._await_future(future)

        self._unsubscribe_ground_truth(data["agent_id"])
        self._unsubscribe_pose_estimate(data["agent_id"])

        self._state_version += 1
        await self.broadcast({
            "type": "info",
            "message": result.message,
            "success": result.success,
            "state_version": self._state_version,
        })

    async def _cmd_configure_sensor(self, ws, data: dict) -> None:
        req = ConfigureSensor.Request()
        req.agent_id = data["agent_id"]
        req.sensor_name = data["sensor_name"]
        req.config_json = json.dumps(data["config"])

        future = self._cli_configure.call_async(req)
        result = await self._await_future(future)

        await ws.send(
            json.dumps({
                "type": "info",
                "message": result.message,
                "success": result.success,
            })
        )

    async def _cmd_remove_sensor(self, ws, data: dict) -> None:
        req = RemoveSensor.Request()
        req.agent_id = data["agent_id"]
        req.sensor_name = data["sensor_name"]

        future = self._cli_remove_sensor.call_async(req)
        result = await self._await_future(future)

        await ws.send(
            json.dumps({
                "type": "info",
                "message": result.message,
                "success": result.success,
            })
        )

    async def _cmd_load_scenario(self, ws, data: dict) -> None:
        req = LoadScenario.Request()
        req.config_yaml = data["config_yaml"]

        future = self._cli_load.call_async(req)
        result = await self._await_future(future)

        await self.broadcast({
            "type": "info",
            "message": result.message,
            "success": result.success,
        })

    async def _cmd_set_pose(self, ws, data: dict) -> None:
        req = SetPose.Request()
        req.agent_id = data["agent_id"]
        req.latitude = float(data.get("lat", 0.0))
        req.longitude = float(data.get("lon", 0.0))
        req.altitude = float(data.get("alt", 0.0))
        req.heading = float(data.get("heading", 0.0))

        future = self._cli_set_pose.call_async(req)
        result = await self._await_future(future)

        if not result.success:
            await ws.send(
                json.dumps({"type": "error", "message": result.message})
            )

    async def _cmd_sim_control(self, ws, data: dict) -> None:
        req = SimControl.Request()
        req.action = data.get("action", "")

        future = self._cli_sim_control.call_async(req)
        result = await self._await_future(future)

        await self.broadcast({
            "type": "sim_status",
            "status": result.status,
            "message": result.message,
            "success": result.success,
        })

    async def _cmd_set_speed(self, ws, data: dict) -> None:
        req = SetSpeed.Request()
        req.speed_multiplier = float(data.get("multiplier", 1.0))

        future = self._cli_set_speed.call_async(req)
        result = await self._await_future(future)

        await self.broadcast({
            "type": "sim_status",
            "speed": result.effective_multiplier,
            "message": result.message,
            "success": result.success,
        })

    async def _cmd_save_scenario(self, ws, data: dict) -> None:
        req = SaveScenario.Request()
        req.file_path = data.get("file_path", "")

        future = self._cli_save.call_async(req)
        result = await self._await_future(future)

        if result.success:
            await ws.send(
                json.dumps({
                    "type": "scenario_saved",
                    "config_yaml": result.config_yaml,
                })
            )
        else:
            await ws.send(
                json.dumps({"type": "error", "message": result.message})
            )

    async def _cmd_subscribe_pose_estimate(self, ws, data: dict) -> None:
        agent_id = data["agent_id"]
        topic = data["topic"]
        self._subscribe_pose_estimate(agent_id, topic)
        await ws.send(
            json.dumps({
                "type": "info",
                "message": f"Subscribed to pose estimate: {topic}",
                "success": True,
            })
        )

    async def _cmd_unsubscribe_pose_estimate(self, ws, data: dict) -> None:
        agent_id = data["agent_id"]
        self._unsubscribe_pose_estimate(agent_id)
        await ws.send(
            json.dumps({
                "type": "info",
                "message": f"Unsubscribed pose estimate for {agent_id}",
                "success": True,
            })
        )

    async def _cmd_get_sensor_types(self, ws, data: dict) -> None:
        from sim_engine.sensors import SENSOR_REGISTRY

        await ws.send(
            json.dumps({
                "type": "sensor_types",
                "types": list(SENSOR_REGISTRY.keys()),
            })
        )

    async def _cmd_get_motion_types(self, ws, data: dict) -> None:
        from sim_engine.motion import MOTION_REGISTRY

        await ws.send(
            json.dumps({
                "type": "motion_types",
                "types": list(MOTION_REGISTRY.keys()),
            })
        )

    async def _cmd_get_state(self, ws, data: dict) -> None:
        """Send full agent state by querying SaveScenario for sensor/config data."""
        import yaml

        agents = {}

        # Try to get full state from SaveScenario service
        try:
            req = SaveScenario.Request()
            req.file_path = ""
            future = self._cli_save.call_async(req)
            result = await self._await_future(future)

            if result.success and result.config_yaml:
                config = yaml.safe_load(result.config_yaml)
                sim_time = config.get("sim", {}).get("sim_time_s", 0.0)

                for agent_id, agent_cfg in config.get("agents", {}).items():
                    pose = agent_cfg.get("initial_pose", {})
                    sensors_cfg = agent_cfg.get("sensors", {})
                    agents[agent_id] = {
                        "lat": pose.get("lat", 0.0),
                        "lon": pose.get("lon", 0.0),
                        "alt": pose.get("alt", 0.0),
                        "heading": pose.get("heading", 0.0),
                        "sensors": list(sensors_cfg.keys()),
                        "sensor_configs": sensors_cfg,
                        "domain_id": agent_cfg.get("domain_id", 0),
                        "vehicle_type": agent_cfg.get("vehicle_type", ""),
                        "vehicle_class": agent_cfg.get("vehicle_class", ""),
                    }
        except Exception as e:
            self.get_logger().error(f"Failed to get state via SaveScenario: {e}")
            # Fall back to ground truth cache
            for agent_id, gt in self._gt_cache.items():
                agents[agent_id] = {
                    "lat": gt.get("lat", 0.0),
                    "lon": gt.get("lon", 0.0),
                    "alt": gt.get("alt", 0.0),
                    "heading": gt.get("heading", 0.0),
                    "sensors": gt.get("sensors", []),
                    "domain_id": gt.get("domain_id", 0),
                    "vehicle_type": gt.get("vehicle_type", ""),
                    "vehicle_class": gt.get("vehicle_class", ""),
                }

        await ws.send(json.dumps({
            "type": "state",
            "data": {"agents": agents},
            "state_version": self._state_version,
        }))

    async def _cmd_push_state(self, ws, data: dict) -> None:
        """Accept full state from the UI (used after backend restart)."""
        ui_agents = data.get("agents", {})
        ui_version = data.get("state_version", 0)

        # Determine which agents to add/remove
        backend_ids = set(self._gt_cache.keys())
        ui_ids = set(ui_agents.keys())

        # Remove backend agents not in UI
        for agent_id in backend_ids - ui_ids:
            try:
                req = RemoveAgent.Request()
                req.agent_id = agent_id
                future = self._cli_remove.call_async(req)
                await self._await_future(future)
                self._unsubscribe_ground_truth(agent_id)
                self._unsubscribe_pose_estimate(agent_id)
            except Exception as e:
                self.get_logger().error(f"push_state remove {agent_id}: {e}")

        # Add UI agents not in backend
        for agent_id in ui_ids - backend_ids:
            agent = ui_agents[agent_id]
            try:
                req = AddAgent.Request()
                req.agent_id = agent_id
                req.latitude = float(agent.get("lat", 0.0))
                req.longitude = float(agent.get("lon", 0.0))
                req.altitude = float(agent.get("alt", 0.0))
                req.heading = float(agent.get("heading", 0.0))
                req.domain_id = int(agent.get("domain_id", 0))
                req.vehicle_type = agent.get("vehicle_type", "")
                req.vehicle_class = agent.get("vehicle_class", "")
                future = self._cli_add.call_async(req)
                await self._await_future(future)
                self._subscribe_ground_truth(agent_id)
            except Exception as e:
                self.get_logger().error(f"push_state add {agent_id}: {e}")

        self._state_version = ui_version
        await self.broadcast({
            "type": "info",
            "message": "State restored from UI",
            "success": True,
            "state_version": self._state_version,
        })

    # -- Clock subscription --------------------------------------------------

    _last_clock_broadcast: float = 0.0

    def _on_clock(self, msg: Clock) -> None:
        """Forward /clock to frontend, throttled to ~10 Hz."""
        sim_time = msg.clock.sec + msg.clock.nanosec * 1e-9
        import time
        now = time.monotonic()
        if now - self._last_clock_broadcast < 0.1:
            return
        self._last_clock_broadcast = now
        self.broadcast_sync({
            "type": "sim_clock",
            "sim_time": sim_time,
        })

    # -- Agent discovery -----------------------------------------------------

    def _discover_agents(self) -> None:
        """Scan for ground truth topics and auto-subscribe to new agents."""
        topic_list = self.get_topic_names_and_types()
        for topic_name, _types in topic_list:
            if topic_name.endswith("/sim/ground_truth"):
                # Extract agent_id from /<agent_id>/sim/ground_truth
                parts = topic_name.strip("/").split("/")
                if len(parts) >= 3:
                    agent_id = parts[0]
                    if agent_id not in self._gt_subs:
                        self._subscribe_ground_truth(agent_id)
                        self.get_logger().info(
                            f"Auto-discovered agent: {agent_id}"
                        )

    # -- Ground truth subscription -------------------------------------------

    def _subscribe_ground_truth(self, agent_id: str) -> None:
        if agent_id in self._gt_subs:
            return
        topic = f"/{agent_id}/sim/ground_truth"

        def callback(msg: GroundTruth, aid=agent_id):
            gt_data = {
                "type": "ground_truth",
                "agent_id": aid,
                "lat": msg.latitude,
                "lon": msg.longitude,
                "alt": msg.altitude,
                "heading": msg.orientation.z,  # simplified; full quat available
            }
            self._gt_cache[aid] = gt_data
            self.broadcast_sync(gt_data)

        self._gt_subs[agent_id] = self.create_subscription(
            GroundTruth, topic, callback, 10
        )

    def _unsubscribe_ground_truth(self, agent_id: str) -> None:
        sub = self._gt_subs.pop(agent_id, None)
        if sub:
            self.destroy_subscription(sub)
        self._gt_cache.pop(agent_id, None)

    # -- Pose estimate subscription ------------------------------------------

    def _subscribe_pose_estimate(self, agent_id: str, topic: str) -> None:
        self._unsubscribe_pose_estimate(agent_id)

        # We subscribe to NavSatFix as a common pose estimate type.
        # This could be made more flexible with dynamic type detection.
        from sensor_msgs.msg import NavSatFix

        def callback(msg: NavSatFix, aid=agent_id):
            self.broadcast_sync({
                "type": "pose_estimate",
                "agent_id": aid,
                "lat": msg.latitude,
                "lon": msg.longitude,
                "alt": msg.altitude,
            })

        self._pose_est_subs[agent_id] = self.create_subscription(
            NavSatFix, topic, callback, 10
        )
        self.get_logger().info(f"Subscribed pose estimate: {agent_id} -> {topic}")

    def _unsubscribe_pose_estimate(self, agent_id: str) -> None:
        sub = self._pose_est_subs.pop(agent_id, None)
        if sub:
            self.destroy_subscription(sub)

    # -- Utilities -----------------------------------------------------------

    async def _await_future(self, future, timeout: float = 5.0):
        """Await a ROS2 service future from async context."""
        deadline = asyncio.get_event_loop().time() + timeout
        while not future.done():
            if asyncio.get_event_loop().time() > deadline:
                raise TimeoutError(f"Service call timed out after {timeout}s")
            await asyncio.sleep(0.05)
        return future.result()


async def ws_handler(ws, node: WsBridgeNode):
    """Handle a single WebSocket connection."""
    node.register_ws(ws)
    node.get_logger().info("WebSocket client connected")
    try:
        async for message in ws:
            try:
                data = json.loads(message)
                await node.handle_command(ws, data)
            except json.JSONDecodeError:
                await ws.send(
                    json.dumps({"type": "error", "message": "Invalid JSON"})
                )
    finally:
        node.unregister_ws(ws)
        node.get_logger().info("WebSocket client disconnected")


async def run_ws_server(node: WsBridgeNode) -> None:
    """Start the WebSocket server."""
    import websockets

    node.set_event_loop(asyncio.get_event_loop())

    async with websockets.serve(
        lambda ws: ws_handler(ws, node),
        "0.0.0.0",
        WS_PORT,
    ):
        node.get_logger().info(f"WebSocket server listening on port {WS_PORT}")
        await asyncio.Future()  # run forever


def main(args=None):
    rclpy.init(args=args)
    node = WsBridgeNode()

    # Run ROS2 executor in a background thread
    executor = MultiThreadedExecutor(num_threads=2)
    executor.add_node(node)
    ros_thread = threading.Thread(target=executor.spin, daemon=True)
    ros_thread.start()

    # Run WebSocket server in the main thread's event loop
    try:
        asyncio.run(run_ws_server(node))
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
