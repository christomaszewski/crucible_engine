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

from sim_msgs.msg import GroundTruth
from sim_msgs.srv import (
    AddAgent,
    ConfigureSensor,
    LoadScenario,
    RemoveAgent,
    SaveScenario,
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
        req.latitude = data.get("lat", 0.0)
        req.longitude = data.get("lon", 0.0)
        req.altitude = data.get("alt", 0.0)
        req.heading = data.get("heading", 0.0)
        req.domain_id = data.get("domain_id", 0)

        future = self._cli_add.call_async(req)
        result = await self._await_future(future)

        # Subscribe to ground truth for this agent
        self._subscribe_ground_truth(data["agent_id"])

        await self.broadcast({
            "type": "info",
            "message": result.message,
            "success": result.success,
        })

    async def _cmd_remove_agent(self, ws, data: dict) -> None:
        req = RemoveAgent.Request()
        req.agent_id = data["agent_id"]

        future = self._cli_remove.call_async(req)
        result = await self._await_future(future)

        self._unsubscribe_ground_truth(data["agent_id"])
        self._unsubscribe_pose_estimate(data["agent_id"])

        await self.broadcast({
            "type": "info",
            "message": result.message,
            "success": result.success,
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
        self.get_logger().info("Subscribed pose estimate: %s -> %s", agent_id, topic)

    def _unsubscribe_pose_estimate(self, agent_id: str) -> None:
        sub = self._pose_est_subs.pop(agent_id, None)
        if sub:
            self.destroy_subscription(sub)

    # -- Utilities -----------------------------------------------------------

    async def _await_future(self, future, timeout: float = 5.0):
        """Await a ROS2 service future from async context."""
        loop = asyncio.get_event_loop()
        result = await asyncio.wait_for(
            loop.run_in_executor(None, lambda: future.result(timeout=timeout)),
            timeout=timeout + 1.0,
        )
        return result


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
        node.get_logger().info("WebSocket server listening on port %d", WS_PORT)
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
