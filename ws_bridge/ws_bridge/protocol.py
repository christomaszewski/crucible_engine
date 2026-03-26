"""WebSocket protocol message definitions.

All messages between the frontend and bridge are JSON with a "cmd" field
for client->server and a "type" field for server->client.
"""

from __future__ import annotations

# -----------------------------------------------------------------------
# Client -> Server commands
# -----------------------------------------------------------------------
# {"cmd": "add_agent", "agent_id": "...", "lat": ..., "lon": ..., "alt": ..., "heading": ..., "domain_id": ...}
# {"cmd": "remove_agent", "agent_id": "..."}
# {"cmd": "configure_sensor", "agent_id": "...", "sensor_name": "...", "config": {...}}
# {"cmd": "remove_sensor", "agent_id": "...", "sensor_name": "..."}
# {"cmd": "set_pose", "agent_id": "...", "lat": ..., "lon": ..., "alt": ..., "heading": ...}
# {"cmd": "set_motion", "agent_id": "...", "config": {...}}
# {"cmd": "load_scenario", "config_yaml": "..."}
# {"cmd": "save_scenario"}
# {"cmd": "sim_control", "action": "pause"|"resume"|"step"|"reset"}
# {"cmd": "set_speed", "multiplier": 2.0}
# {"cmd": "subscribe_pose_estimate", "agent_id": "...", "topic": "..."}
# {"cmd": "unsubscribe_pose_estimate", "agent_id": "..."}
# {"cmd": "get_state"}
# {"cmd": "get_sensor_types"}
# {"cmd": "get_motion_types"}
#
# Stack orchestration:
# {"cmd": "launch_stack", "agent_id": "...", "compose_file": "...", "env": {...}}
# {"cmd": "stop_stack", "agent_id": "..."}
# {"cmd": "get_stack_status"}

# -----------------------------------------------------------------------
# Server -> Client messages
# -----------------------------------------------------------------------
# {"type": "state", "data": {...}}              -- periodic world state snapshot
# {"type": "pose_estimate", "agent_id": "...", "lat": ..., "lon": ..., ...}
# {"type": "ground_truth", "agent_id": "...", "lat": ..., "lon": ..., ...}
# {"type": "scenario_saved", "config_yaml": "..."}
# {"type": "sensor_types", "types": [...]}
# {"type": "motion_types", "types": [...]}
# {"type": "error", "message": "..."}
# {"type": "info", "message": "..."}
# {"type": "stack_status", "stacks": {...}}
# {"type": "event_fired", "event": {...}}
