# crucible_engine

Simulation engine, WebSocket bridge, and web frontend for the CRUCIBLE SITL framework.

## Packages

### sim_engine
ROS2 Python node that runs the simulation loop. Manages agents, sensor models, motion models, ground truth publishing, and scenario event execution.

### ws_bridge
ROS2 Python node + WebSocket server that bridges the web frontend to the sim engine's ROS2 services and topics.

### frontend
Vanilla HTML/JS/CSS web UI served by nginx. Leaflet map with click-to-place agents, sensor configuration, real-time pose estimate overlay, scenario load/save, stack orchestration controls, and sim playback control.

## Sensor Plugins
Built-in: `navsatfix`, `imu`, `altimeter`, `twr_radio`

Custom sensors can be added via separate ROS2 packages that implement the `SensorModel` ABC and register via Python entry points.

## Motion Plugins
Built-in: `static`, `waypoint`, `commanded_velocity`

Part of the [CRUCIBLE](https://github.com/TODO/crucible) framework.
