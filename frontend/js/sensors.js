/**
 * Sensors module — sensor configuration dialogs and rendering.
 */

const Sensors = (() => {
    const SENSOR_DEFAULTS = {
        navsatfix: {
            type: 'navsatfix',
            topic_suffix: 'gps/fix',
            rate_hz: 5,
            noise: { horizontal_std_m: 1.5, vertical_std_m: 3.0 },
        },
        imu: {
            type: 'imu',
            topic_suffix: 'imu/data',
            rate_hz: 50,
            noise: { accel_std: 0.01, gyro_std: 0.001, orientation_std: 0.005 },
        },
        altimeter: {
            type: 'altimeter',
            topic_suffix: 'altimeter/data',
            rate_hz: 10,
            noise: { std_m: 0.5 },
        },
        twr_radio: {
            type: 'twr_radio',
            topic_suffix: 'twr/ranges',
            rate_hz: 1,
            max_range_m: 500,
            noise: { std_m: 0.1 },
        },
    };

    const MSG_TYPE_MAP = {
        navsatfix: 'sensor_msgs/NavSatFix',
        imu: 'sensor_msgs/Imu',
        altimeter: 'std_msgs/Float64',
        twr_radio: 'crucible_msgs/RangeArray',
    };

    function renderSensorConfig(agentId, sensorNames) {
        const area = document.getElementById('sensor-config-area');
        if (!area) return;

        if (!sensorNames || sensorNames.length === 0) {
            area.innerHTML = '<div style="color: var(--text-muted); font-size: 11px;">No sensors configured</div>';
            return;
        }

        const agent = Agents.getAll()[agentId];
        const configs = agent?.sensor_configs || {};

        area.innerHTML = sensorNames.map(name => {
            const cfg = configs[name] || SENSOR_DEFAULTS[name] || {};
            const sensorType = cfg.type || name;
            const topicSuffix = cfg.topic_suffix || SENSOR_DEFAULTS[sensorType]?.topic_suffix || name;
            const rateHz = cfg.rate_hz ?? SENSOR_DEFAULTS[sensorType]?.rate_hz ?? '?';
            const msgType = MSG_TYPE_MAP[sensorType] || 'unknown';
            const fullTopic = `/${agentId}/${topicSuffix}`;
            const noise = cfg.noise || {};
            const noiseRows = Object.entries(noise).map(([k, v]) =>
                `<div class="sensor-detail-row"><span class="sensor-detail-key">${k}</span><span>${v}</span></div>`
            ).join('');

            // Extra fields (max_range_m, use_agl, etc.)
            const skipKeys = new Set(['type', 'topic_suffix', 'rate_hz', 'noise', 'seed']);
            const extraRows = Object.entries(cfg)
                .filter(([k]) => !skipKeys.has(k))
                .map(([k, v]) =>
                    `<div class="sensor-detail-row"><span class="sensor-detail-key">${k}</span><span>${v}</span></div>`
                ).join('');

            return `
                <div class="sensor-card" data-sensor="${name}">
                    <div class="sensor-card-header">
                        <span class="sensor-badge">${name}</span>
                        <span class="sensor-card-toggle">&#9662;</span>
                    </div>
                    <div class="sensor-card-body">
                        <div class="sensor-detail-row"><span class="sensor-detail-key">topic</span><span class="sensor-detail-topic">${fullTopic}</span></div>
                        <div class="sensor-detail-row"><span class="sensor-detail-key">msg_type</span><span>${msgType}</span></div>
                        <div class="sensor-detail-row"><span class="sensor-detail-key">rate_hz</span><span>${rateHz}</span></div>
                        ${extraRows}
                        ${noiseRows ? '<div class="sensor-detail-divider">noise</div>' + noiseRows : ''}
                        <button class="btn btn-sm btn-danger sensor-remove-btn" data-remove-sensor="${name}">Remove</button>
                    </div>
                </div>
            `;
        }).join('');

        // Toggle expand/collapse
        area.querySelectorAll('.sensor-card-header').forEach(header => {
            header.addEventListener('click', () => {
                header.parentElement.classList.toggle('expanded');
            });
        });

        // Remove sensor handlers
        area.querySelectorAll('[data-remove-sensor]').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                removeSensor(agentId, btn.dataset.removeSensor);
            });
        });
    }

    function showAddSensorDialog(agentId) {
        const types = Object.keys(SENSOR_DEFAULTS);

        // Simple prompt-style: use a small inline dialog
        const area = document.getElementById('sensor-config-area');
        const existingSensors = Agents.getAll()[agentId]?.sensors || [];

        // Filter out already-added sensors
        const available = types.filter(t => !existingSensors.includes(t));

        if (available.length === 0) {
            App.toast('All sensor types already added', 'info');
            return;
        }

        const selector = document.createElement('div');
        selector.style.cssText = 'display: flex; gap: 4px; flex-wrap: wrap; margin-top: 8px;';
        selector.innerHTML = available.map(type =>
            `<button class="btn btn-sm btn-accent" data-add-type="${type}">${type}</button>`
        ).join('');

        area.appendChild(selector);

        selector.querySelectorAll('[data-add-type]').forEach(btn => {
            btn.addEventListener('click', () => {
                addSensor(agentId, btn.dataset.addType);
                selector.remove();
            });
        });
    }

    function addSensor(agentId, sensorType) {
        const config = JSON.parse(JSON.stringify(SENSOR_DEFAULTS[sensorType] || {}));
        config.type = sensorType;

        WS.sendBridge({
            cmd: 'configure_sensor',
            agent_id: agentId,
            sensor_name: sensorType,
            config: config,
        });

        // Update local state
        const agent = Agents.getAll()[agentId];
        if (agent) {
            if (!agent.sensors) agent.sensors = [];
            if (!agent.sensors.includes(sensorType)) {
                agent.sensors.push(sensorType);
            }
            if (!agent.sensor_configs) agent.sensor_configs = {};
            agent.sensor_configs[sensorType] = config;
        }

        // Re-render
        Agents.selectAgent(agentId);
        Agents.updateSummary();
        App.toast(`Added ${sensorType} to ${agentId}`, 'success');
    }

    function removeSensor(agentId, sensorName) {
        // Send empty config to effectively remove
        WS.sendBridge({
            cmd: 'remove_sensor',
            agent_id: agentId,
            sensor_name: sensorName,
        });

        const agent = Agents.getAll()[agentId];
        if (agent) {
            if (agent.sensors) {
                agent.sensors = agent.sensors.filter(s => s !== sensorName);
            }
            if (agent.sensor_configs) {
                delete agent.sensor_configs[sensorName];
            }
        }

        Agents.selectAgent(agentId);
        Agents.updateSummary();
        App.toast(`Removed ${sensorName} from ${agentId}`);
    }

    return {
        renderSensorConfig,
        showAddSensorDialog,
        addSensor,
        removeSensor,
        SENSOR_DEFAULTS,
    };
})();
