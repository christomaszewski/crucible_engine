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

    // Keys that are read-only info (not editable)
    const READ_ONLY_KEYS = new Set(['type', 'seed']);
    // Keys shown in the header summary, not repeated in body
    const SKIP_IN_BODY = new Set(['type', 'seed', 'noise']);

    function _buildConfig(agentId, sensorName, configs) {
        const cfg = configs[sensorName] || SENSOR_DEFAULTS[sensorName] || {};
        const sensorType = cfg.type || sensorName;
        return {
            cfg,
            sensorType,
            topicSuffix: cfg.topic_suffix || SENSOR_DEFAULTS[sensorType]?.topic_suffix || sensorName,
            rateHz: cfg.rate_hz ?? SENSOR_DEFAULTS[sensorType]?.rate_hz ?? '?',
            msgType: MSG_TYPE_MAP[sensorType] || 'unknown',
            noise: cfg.noise || {},
        };
    }

    function _editableValue(key, value, isNoise) {
        const editable = !READ_ONLY_KEYS.has(key);
        const dataAttr = isNoise ? `data-noise-key="${key}"` : `data-cfg-key="${key}"`;
        if (editable) {
            return `<span class="sensor-val editable" ${dataAttr} tabindex="0">${value}</span>`;
        }
        return `<span class="sensor-val">${value}</span>`;
    }

    function renderSensorConfig(agentId, sensorNames) {
        const area = document.getElementById('sensor-config-area');
        if (!area) return;

        const agent = Agents.getAll()[agentId];
        const configs = agent?.sensor_configs || {};

        if (!sensorNames || sensorNames.length === 0) {
            area.innerHTML = '<div style="color: var(--text-muted); font-size: 11px;">No sensors configured</div>';
            return;
        }

        area.innerHTML = sensorNames.map(name => {
            const { cfg, sensorType, topicSuffix, rateHz, msgType, noise } = _buildConfig(agentId, name, configs);
            const fullTopic = `/${agentId}/${topicSuffix}`;

            // Body rows: editable config fields (skip type, seed, noise — noise gets its own section)
            const cfgRows = Object.entries(cfg)
                .filter(([k]) => !SKIP_IN_BODY.has(k))
                .map(([k, v]) =>
                    `<div class="sensor-row"><span class="sensor-key">${k}</span>${_editableValue(k, v, false)}</div>`
                ).join('');

            // Noise rows
            const noiseRows = Object.entries(noise).map(([k, v]) =>
                `<div class="sensor-row"><span class="sensor-key">${k}</span>${_editableValue(k, v, true)}</div>`
            ).join('');

            return `
                <div class="sensor-card" data-sensor="${name}">
                    <div class="sensor-card-header">
                        <div class="sensor-card-title">
                            <span class="sensor-card-name">${name}</span>
                            <span class="sensor-card-info">${msgType} · ${rateHz} Hz</span>
                        </div>
                        <span class="sensor-card-chevron"></span>
                    </div>
                    <div class="sensor-card-body">
                        <div class="sensor-row sensor-row-topic">
                            <span class="sensor-key">topic</span>
                            <span class="sensor-val topic">${fullTopic}</span>
                        </div>
                        ${cfgRows}
                        ${noiseRows ? `<div class="sensor-group-label">noise</div>${noiseRows}` : ''}
                        <div class="sensor-card-actions">
                            <button class="btn btn-sm btn-danger" data-remove-sensor="${name}">Remove Sensor</button>
                        </div>
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

        // Editable value click-to-edit
        area.querySelectorAll('.sensor-val.editable').forEach(el => {
            el.addEventListener('click', (e) => {
                e.stopPropagation();
                _startInlineEdit(el, agentId);
            });
            el.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') { e.preventDefault(); _startInlineEdit(el, agentId); }
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

    function _startInlineEdit(el, agentId) {
        if (el.querySelector('input')) return; // already editing
        const currentVal = el.textContent;
        const input = document.createElement('input');
        input.type = 'text';
        input.className = 'sensor-inline-input';
        input.value = currentVal;

        el.textContent = '';
        el.appendChild(input);
        input.focus();
        input.select();

        const commit = () => {
            const newVal = input.value.trim();
            el.textContent = newVal || currentVal;
            if (newVal && newVal !== currentVal) {
                _applyEdit(el, agentId, newVal);
            }
        };

        input.addEventListener('blur', commit);
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') { e.preventDefault(); input.blur(); }
            if (e.key === 'Escape') { el.textContent = currentVal; }
        });
    }

    function _applyEdit(el, agentId, newVal) {
        const card = el.closest('.sensor-card');
        const sensorName = card.dataset.sensor;
        const agent = Agents.getAll()[agentId];
        if (!agent) return;

        const cfg = agent.sensor_configs?.[sensorName]
            || JSON.parse(JSON.stringify(SENSOR_DEFAULTS[sensorName] || {}));

        // Parse numeric values
        const parsed = isNaN(newVal) ? newVal : parseFloat(newVal);

        if (el.dataset.noiseKey) {
            if (!cfg.noise) cfg.noise = {};
            cfg.noise[el.dataset.noiseKey] = parsed;
        } else if (el.dataset.cfgKey) {
            cfg[el.dataset.cfgKey] = parsed;
        }

        // Update local state
        if (!agent.sensor_configs) agent.sensor_configs = {};
        agent.sensor_configs[sensorName] = cfg;

        // Send to backend
        WS.sendBridge({
            cmd: 'configure_sensor',
            agent_name: agentId,
            sensor_name: sensorName,
            config: cfg,
        });

        App.toast(`Updated ${sensorName} config`, 'success');
    }

    function showAddSensorDialog(agentId) {
        const types = Object.keys(SENSOR_DEFAULTS);
        const area = document.getElementById('sensor-config-area');
        const existingSensors = Agents.getAll()[agentId]?.sensors || [];
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
            agent_name: agentId,
            sensor_name: sensorType,
            config: config,
        });

        const agent = Agents.getAll()[agentId];
        if (agent) {
            if (!agent.sensors) agent.sensors = [];
            if (!agent.sensors.includes(sensorType)) {
                agent.sensors.push(sensorType);
            }
            if (!agent.sensor_configs) agent.sensor_configs = {};
            agent.sensor_configs[sensorType] = config;
        }

        Agents.refreshDetail(agentId);
        Agents.updateSummary();
        App.toast(`Added ${sensorType} to ${agentId}`, 'success');
    }

    function removeSensor(agentId, sensorName) {
        WS.sendBridge({
            cmd: 'remove_sensor',
            agent_name: agentId,
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

        Agents.refreshDetail(agentId);
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
