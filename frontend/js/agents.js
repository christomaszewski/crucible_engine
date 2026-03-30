/**
 * Agents module — manages agent state, list UI, selection, and CRUD.
 */

const Agents = (() => {
    const agents = {};  // agent_name -> { lat, lon, alt, heading, sensors, domain_id, vehicle_type, vehicle_class, stack_status }
    let selectedId = null;
    let lastKnownVersion = 0;  // last state_version received from backend
    let sortMode = 'id';  // 'id', 'type', 'altitude'
    let sortAscending = true;

    function getAll() { return agents; }
    function getSelected() { return selectedId; }

    function addAgent(data) {
        const id = data.agent_name;
        agents[id] = {
            lat: data.lat || 0,
            lon: data.lon || 0,
            alt: data.alt || 0,
            heading: data.heading || 0,
            sensors: data.sensors || [],
            sensor_configs: data.sensor_configs || {},
            domain_id: data.domain_id || 0,
            vehicle_type: data.vehicle_type || '',
            vehicle_class: data.vehicle_class || '',
            stack_status: 'STOPPED',
            stack_compose_file: data.stack_compose_file || '',
            stack_env: data.stack_env || {},
            stack_sys_env: data.stack_sys_env || {
                AGENT_ID: true,
                AGENT_NAME: true,
                ROS_DOMAIN_ID: true,
                AGENT_NAMESPACE: true,
                FLEET_SIZE: true,
                FLEET_AGENTS: true,
            },
            stack_sys_env_remap: data.stack_sys_env_remap || {},
        };

        MapView.addAgent(id, agents[id].lat, agents[id].lon, agents[id].heading);
        renderList();
        updateSummary();
    }

    function removeAgent(agentId) {
        WS.sendBridge({ cmd: 'remove_agent', agent_name: agentId });
        Accuracy.removeAgent(agentId);
        delete agents[agentId];
        MapView.removeAgent(agentId);
        if (selectedId === agentId) {
            selectedId = null;
            hideDetail();
        }
        renderList();
        updateSummary();
        if (typeof App !== 'undefined' && App.updatePlaceButton) App.updatePlaceButton();
    }

    function updateGroundTruth(data) {
        let agent = agents[data.agent_name];
        if (!agent) {
            // Auto-create agent from ground truth (e.g. loaded from scenario)
            addAgent({
                agent_name: data.agent_name,
                lat: data.lat,
                lon: data.lon,
                alt: data.alt,
                heading: data.heading,
                sensors: [],
                domain_id: 0,
            });
            return;
        }
        agent.lat = data.lat;
        agent.lon = data.lon;
        agent.alt = data.alt;
        agent.heading = data.heading;
        MapView.updateAgent(data.agent_name, data.lat, data.lon, data.heading);
        // Live-update detail panel if this agent is selected
        if (selectedId === data.agent_name) _updateDetailValues(data.agent_name);
    }

    function selectAgent(agentId) {
        if (selectedId === agentId) {
            // Toggle off if clicking the same agent
            selectedId = null;
            MapView.selectAgent(null);
            hideDetail();
            renderList();
            if (typeof App !== 'undefined' && App.updateHotkeyOverlay) App.updateHotkeyOverlay();
            return;
        }
        selectedId = agentId;
        MapView.selectAgent(agentId);
        renderList();
        showDetail(agentId);
        if (typeof App !== 'undefined' && App.updateHotkeyOverlay) App.updateHotkeyOverlay();
    }

    function setSortMode(mode) {
        sortMode = mode;
        renderList();
    }

    function toggleSortDirection() {
        sortAscending = !sortAscending;
        renderList();
    }

    function isSortAscending() { return sortAscending; }

    function _isUuv(id) {
        const a = agents[id];
        return (a.vehicle_type || Icons.getTypeFromId(id)).toLowerCase() === 'uuv';
    }

    function _altLabel(id) {
        return _isUuv(id) ? 'Depth' : 'Alt';
    }

    function _altDisplay(id) {
        const alt = agents[id].alt || 0;
        return _isUuv(id) ? Math.abs(alt).toFixed(1) : alt.toFixed(1);
    }

    function _agentCardHtml(id) {
        const a = agents[id];
        const selected = id === selectedId ? 'selected' : '';
        const vtype = (a.vehicle_type || Icons.getTypeFromId(id)).toLowerCase();
        const sensorBadges = (a.sensors || [])
            .map(s => `<span class="sensor-badge">${s}</span>`)
            .join('');
        const statusClass = (a.stack_status || 'STOPPED').toLowerCase();

        return `
            <div class="agent-card ${selected}" data-id="${id}">
                <div class="agent-card-header">
                    <span class="agent-id">
                        <span class="agent-type-icon type-${vtype}">${Icons.getSvg(vtype)}</span>
                        ${id}
                    </span>
                    <span class="agent-status ${statusClass}"></span>
                </div>
                <div class="agent-meta">
                    ${a.lat.toFixed(6)}, ${a.lon.toFixed(6)} | ${_altLabel(id)}: ${_altDisplay(id)}m
                </div>
                <div class="agent-sensors">${sensorBadges}</div>
            </div>
        `;
    }

    function renderList() {
        const list = document.getElementById('agent-list');
        const ids = Object.keys(agents).sort();
        const dir = sortAscending ? 1 : -1;
        document.getElementById('agent-count').textContent = ids.length;

        // Apply sort direction to ID-sorted list
        const sortedIds = sortAscending ? ids : [...ids].reverse();

        let html = '';

        if (sortMode === 'type') {
            const typeOrder = sortAscending
                ? ['uav', 'usv', 'ugv', 'uuv', 'uxv']
                : ['uxv', 'uuv', 'ugv', 'usv', 'uav'];
            const groups = {};
            for (const id of ids) {
                const vtype = (agents[id].vehicle_type || Icons.getTypeFromId(id)).toLowerCase();
                (groups[vtype] = groups[vtype] || []).push(id);
            }
            // Reverse within-group order if descending
            if (!sortAscending) {
                for (const arr of Object.values(groups)) arr.reverse();
            }
            for (const t of typeOrder) {
                if (!groups[t] || groups[t].length === 0) continue;
                html += `<div class="agent-group-header">${Icons.getLabel(t)}</div>`;
                html += groups[t].map(_agentCardHtml).join('');
            }
            // Any types not in typeOrder
            for (const t of Object.keys(groups)) {
                if (typeOrder.includes(t)) continue;
                html += `<div class="agent-group-header">${t.toUpperCase()}</div>`;
                html += groups[t].map(_agentCardHtml).join('');
            }
        } else if (sortMode === 'altitude') {
            const sorted = [...ids].sort((a, b) =>
                dir * ((agents[a].alt || 0) - (agents[b].alt || 0))
            );
            html = sorted.map(_agentCardHtml).join('');
        } else {
            html = sortedIds.map(_agentCardHtml).join('');
        }

        list.innerHTML = html;

        // Click handlers
        list.querySelectorAll('.agent-card').forEach(card => {
            card.addEventListener('click', () => {
                selectAgent(card.dataset.id);
            });
        });
    }

    function showDetail(agentId) {
        const panel = document.getElementById('detail-panel');
        const agent = agents[agentId];
        if (!agent) {
            hideDetail();
            return;
        }

        const dvtype = (agent.vehicle_type || Icons.getTypeFromId(agentId)).toLowerCase();
        const isUuv = dvtype === 'uuv';
        const altLabel = isUuv ? 'Depth' : 'Altitude';
        const noAlt = dvtype === 'ugv' || dvtype === 'usv';
        const running = SimControl.getStatus() === 'RUNNING';
        const editClass = running ? 'pose-val readonly' : 'pose-val editable';

        panel.innerHTML = `
            <button class="detail-close" id="detail-close">&times;</button>
            <div class="detail-section">
                <div class="detail-title">
                    <span class="agent-type-icon type-${dvtype}">${Icons.getSvg(dvtype)}</span>
                    Agent: ${agentId}
                </div>
                <div class="pose-row">
                    <span class="pose-label">Type</span>
                    <span class="pose-val">${Icons.getLabel(dvtype)}${agent.vehicle_class ? ' / ' + agent.vehicle_class : ''}</span>
                </div>
                <div class="pose-row">
                    <span class="pose-label">DDS Domain</span>
                    <span class="pose-val">${agent.domain_id}</span>
                </div>
                <div class="pose-row">
                    <span class="pose-label">Latitude</span>
                    <span class="${editClass}" id="detail-lat" data-field="lat">${agent.lat.toFixed(6)}</span>
                </div>
                <div class="pose-row">
                    <span class="pose-label">Longitude</span>
                    <span class="${editClass}" id="detail-lon" data-field="lon">${agent.lon.toFixed(6)}</span>
                </div>
                <div class="pose-row">
                    <span class="pose-label">Heading</span>
                    <span class="${editClass}" id="detail-heading" data-field="heading">${((agent.heading || 0) * 180 / Math.PI).toFixed(1)}&deg;</span>
                </div>
                ${noAlt ? '' : `
                <div class="pose-row">
                    <span class="pose-label">${altLabel}</span>
                    <span class="${editClass}" id="detail-alt" data-field="alt">${isUuv ? Math.abs(agent.alt).toFixed(1) : agent.alt.toFixed(1)}m</span>
                </div>
                `}
            </div>
            <div class="detail-section">
                <div class="detail-title">Sensors</div>
                <div id="sensor-config-area"></div>
                <button class="btn btn-sm" id="btn-add-sensor" style="margin-top: 8px;">+ Add Sensor</button>
            </div>
            <div class="detail-section">
                <div class="detail-title">Stack <span class="sensor-badge" style="margin-left: 6px;">${agent.stack_status}</span></div>
                <div class="pose-row">
                    <span class="pose-label">Compose</span>
                    <span class="pose-val editable" id="detail-compose" data-field="stack_compose_file" title="${agent.stack_compose_file || 'not set'}">${agent.stack_compose_file || '<em>not set</em>'}</span>
                </div>
                <div class="sys-env-toggle" id="sys-env-toggle">System Env <span class="sys-env-arrow" id="sys-env-arrow">&#9654;</span></div>
                <div class="sys-env-area collapsed" id="sys-env-area"></div>
                <div class="stack-env-label">User Env</div>
                <div class="stack-env-area" id="stack-env-area"></div>
                <div style="margin-top: 8px; display: flex; gap: 4px;">
                    <button class="btn btn-sm btn-accent" id="btn-launch-stack">Launch</button>
                    <button class="btn btn-sm btn-danger" id="btn-stop-stack">Stop</button>
                </div>
            </div>
            <div class="detail-section">
                <button class="btn btn-sm btn-danger" id="btn-remove-agent">Remove Agent</button>
            </div>
        `;

        panel.classList.add('visible');

        // Close button
        document.getElementById('detail-close').addEventListener('click', () => {
            selectedId = null;
            MapView.selectAgent(null);
            hideDetail();
            renderList();
            if (typeof App !== 'undefined' && App.updateHotkeyOverlay) App.updateHotkeyOverlay();
        });

        // Click-to-edit on pose values (sensor config style)
        panel.querySelectorAll('.pose-val.editable').forEach(el => {
            el.addEventListener('click', () => _startPoseEdit(el, agentId));
        });

        // Clicking anywhere outside an active pose input commits it
        panel.addEventListener('mousedown', (e) => {
            if (!e.target.closest('.pose-inline-input')) {
                const active = panel.querySelector('.pose-inline-input');
                if (active) active.blur();
            }
        });
        document.getElementById('map').addEventListener('mousedown', () => {
            const active = panel.querySelector('.pose-inline-input');
            if (active) active.blur();
        });

        // Event listeners
        document.getElementById('btn-add-sensor').addEventListener('click', () => {
            Sensors.showAddSensorDialog(agentId);
        });

        document.getElementById('btn-remove-agent').addEventListener('click', () => {
            removeAgent(agentId);
        });

        document.getElementById('btn-launch-stack').addEventListener('click', () => {
            Orchestrator.launchStack(agentId);
        });

        document.getElementById('btn-stop-stack').addEventListener('click', () => {
            Orchestrator.stopStack(agentId);
        });

        // Render sensor configs
        Sensors.renderSensorConfig(agentId, agent.sensors || []);

        // System env — collapsible toggle
        document.getElementById('sys-env-toggle').addEventListener('click', () => {
            const area = document.getElementById('sys-env-area');
            const arrow = document.getElementById('sys-env-arrow');
            area.classList.toggle('collapsed');
            arrow.innerHTML = area.classList.contains('collapsed') ? '&#9654;' : '&#9660;';
        });
        _renderSysEnv(agentId);

        // Render user stack env vars
        _renderStackEnv(agentId);
    }

    function _computeSysEnvValues(agentId) {
        const agent = agents[agentId];
        if (!agent) return {};
        const match = agentId.match(/_(\d+)$/);
        const agentIdNum = match ? String(parseInt(match[1], 10)) : '0';
        const allIds = Object.keys(agents);
        return {
            AGENT_ID: agentIdNum,
            AGENT_NAME: agentId,
            ROS_DOMAIN_ID: String(agent.domain_id),
            AGENT_NAMESPACE: agentId,
            FLEET_SIZE: String(allIds.length),
            FLEET_AGENTS: allIds.join(','),
        };
    }

    function _renderSysEnv(agentId) {
        const area = document.getElementById('sys-env-area');
        if (!area) return;
        const agent = agents[agentId];
        if (!agent) return;
        const sysFlags = agent.stack_sys_env || {};
        const remaps = agent.stack_sys_env_remap || {};
        const values = _computeSysEnvValues(agentId);

        area.innerHTML = Object.entries(values).sort(([a], [b]) => a.localeCompare(b)).map(([key, val]) => {
            const checked = sysFlags[key] !== false ? 'checked' : '';
            const remap = remaps[key] || '';
            const remapClass = remap ? 'sys-env-remap active' : 'sys-env-remap';
            return `<div class="sys-env-row">
                <label class="sys-env-check"><input type="checkbox" data-sys-key="${key}" ${checked}></label>
                <span class="sys-env-key">${key}</span>
                <span class="${remapClass}" data-sys-key="${key}" title="Click to remap variable name">${remap ? '&rarr; ' + remap : '&rarr;'}</span>
                <span class="sys-env-val">${val}</span>
            </div>`;
        }).join('');

        // Checkbox handlers
        area.querySelectorAll('input[type="checkbox"]').forEach(cb => {
            cb.addEventListener('change', () => {
                if (!agent.stack_sys_env) agent.stack_sys_env = {};
                agent.stack_sys_env[cb.dataset.sysKey] = cb.checked;
            });
        });

        // Remap click-to-edit handlers
        area.querySelectorAll('.sys-env-remap').forEach(el => {
            el.addEventListener('click', () => _startRemapEdit(el, agent));
        });
    }

    function _startRemapEdit(el, agent) {
        if (el.querySelector('input')) return;
        const key = el.dataset.sysKey;
        if (!agent.stack_sys_env_remap) agent.stack_sys_env_remap = {};
        const currentVal = agent.stack_sys_env_remap[key] || '';

        const input = document.createElement('input');
        input.type = 'text';
        input.className = 'pose-inline-input sys-env-remap-input';
        input.value = currentVal;
        input.placeholder = key;

        el.textContent = '';
        const arrow = document.createElement('span');
        arrow.textContent = '\u2192 ';
        arrow.style.opacity = '0.5';
        el.appendChild(arrow);
        el.appendChild(input);
        input.focus();
        input.select();

        const commit = () => {
            const newVal = input.value.trim().toUpperCase();
            if (newVal && newVal !== key) {
                agent.stack_sys_env_remap[key] = newVal;
                el.className = 'sys-env-remap active';
            } else {
                delete agent.stack_sys_env_remap[key];
                el.className = 'sys-env-remap';
            }
            el.innerHTML = agent.stack_sys_env_remap[key]
                ? '&rarr; ' + agent.stack_sys_env_remap[key]
                : '&rarr;';
        };
        input.addEventListener('blur', commit);
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') { e.preventDefault(); input.blur(); }
            if (e.key === 'Escape') {
                el.innerHTML = currentVal ? '&rarr; ' + currentVal : '&rarr;';
            }
        });
    }

    function _renderStackEnv(agentId) {
        const area = document.getElementById('stack-env-area');
        if (!area) return;
        const agent = agents[agentId];
        if (!agent) return;
        const env = agent.stack_env || {};
        const entries = Object.entries(env);

        if (entries.length === 0) {
            area.innerHTML = '<div style="color: var(--text-muted); font-size: 10px; margin-top: 4px;">No env vars</div>';
        } else {
            area.innerHTML = entries.map(([k, v]) =>
                `<div class="pose-row"><span class="pose-label" style="font-size:10px">${k}</span><span class="pose-val editable" data-env-key="${k}" style="font-size:10px">${v}</span></div>`
            ).join('');
        }

        // Add env button
        const addBtn = document.createElement('button');
        addBtn.className = 'btn btn-sm';
        addBtn.style.marginTop = '4px';
        addBtn.style.fontSize = '10px';
        addBtn.textContent = '+ Env Var';
        addBtn.addEventListener('click', () => {
            const key = prompt('Environment variable name:');
            if (!key || !key.trim()) return;
            const val = prompt(`Value for ${key.trim()}:`, '');
            if (val === null) return;
            if (!agent.stack_env) agent.stack_env = {};
            agent.stack_env[key.trim()] = val;
            _renderStackEnv(agentId);
        });
        area.appendChild(addBtn);

        // Click-to-edit env values
        area.querySelectorAll('.pose-val.editable').forEach(el => {
            el.addEventListener('click', () => {
                if (el.querySelector('input')) return;
                const envKey = el.dataset.envKey;
                const currentVal = el.textContent;
                const input = document.createElement('input');
                input.type = 'text';
                input.className = 'pose-inline-input';
                input.style.width = '80px';
                input.value = currentVal;

                el.textContent = '';
                el.appendChild(input);
                input.focus();
                input.select();

                const commit = () => {
                    const newVal = input.value.trim();
                    if (!agent.stack_env) agent.stack_env = {};
                    agent.stack_env[envKey] = newVal;
                    el.textContent = newVal;
                };
                input.addEventListener('blur', commit);
                input.addEventListener('keydown', (e) => {
                    if (e.key === 'Enter') { e.preventDefault(); input.blur(); }
                    if (e.key === 'Escape') { el.textContent = currentVal; }
                });
            });
        });
    }

    function _startPoseEdit(el, agentId) {
        if (el.querySelector('input')) return;
        const field = el.dataset.field;
        const agent = agents[agentId];
        if (!agent) return;

        const dvtype = (agent.vehicle_type || Icons.getTypeFromId(agentId)).toLowerCase();
        const isUuv = dvtype === 'uuv';

        // Text fields (compose file path)
        if (field === 'stack_compose_file') {
            const rawVal = agent.stack_compose_file || '';
            const input = document.createElement('input');
            input.type = 'text';
            input.className = 'pose-inline-input';
            input.style.width = '140px';
            input.value = rawVal;
            input.placeholder = '/opt/stacks/agent_stack.yml';

            el.textContent = '';
            el.appendChild(input);
            input.focus();
            input.select();

            const commit = () => {
                const newVal = input.value.trim();
                agent.stack_compose_file = newVal;
                el.innerHTML = newVal || '<em>not set</em>';
                el.title = newVal || 'not set';
            };
            input.addEventListener('blur', commit);
            input.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') { e.preventDefault(); input.blur(); }
                if (e.key === 'Escape') { el.innerHTML = agent.stack_compose_file || '<em>not set</em>'; }
            });
            return;
        }

        // Numeric fields (lat, lon, heading, alt)
        let rawVal;
        if (field === 'heading') {
            rawVal = ((agent.heading || 0) * 180 / Math.PI).toFixed(1);
        } else if (field === 'alt') {
            rawVal = isUuv ? Math.abs(agent.alt).toFixed(1) : agent.alt.toFixed(1);
        } else {
            rawVal = agent[field]?.toFixed(6) ?? '0';
        }

        const input = document.createElement('input');
        input.type = 'number';
        input.step = (field === 'lat' || field === 'lon') ? 'any' : '0.1';
        input.className = 'pose-inline-input';
        input.value = rawVal;

        el.textContent = '';
        el.appendChild(input);
        input.focus();
        input.select();

        const commit = () => {
            const newVal = parseFloat(input.value);
            if (isNaN(newVal)) {
                _updateDetailValues(agentId);
                return;
            }

            if (field === 'lat') agent.lat = newVal;
            else if (field === 'lon') agent.lon = newVal;
            else if (field === 'heading') agent.heading = newVal * Math.PI / 180;
            else if (field === 'alt') agent.alt = isUuv ? -Math.abs(newVal) : Math.max(0, newVal);

            WS.sendBridge({
                cmd: 'set_pose',
                agent_name: agentId,
                lat: agent.lat,
                lon: agent.lon,
                alt: agent.alt,
                heading: agent.heading,
            });
            MapView.updateAgent(agentId, agent.lat, agent.lon, agent.heading);
            _updateDetailValues(agentId);
            renderList();
        };

        input.addEventListener('blur', commit);
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') { e.preventDefault(); input.blur(); }
            if (e.key === 'Escape') { _updateDetailValues(agentId); }
        });
    }

    function _updateDetailValues(agentId) {
        const agent = agents[agentId];
        if (!agent) return;
        const dvtype = (agent.vehicle_type || Icons.getTypeFromId(agentId)).toLowerCase();
        const isUuv = dvtype === 'uuv';

        const latEl = document.getElementById('detail-lat');
        const lonEl = document.getElementById('detail-lon');
        const hdgEl = document.getElementById('detail-heading');
        const altEl = document.getElementById('detail-alt');

        // Only update if not currently being edited (no child input)
        if (latEl && !latEl.querySelector('input')) latEl.textContent = agent.lat.toFixed(6);
        if (lonEl && !lonEl.querySelector('input')) lonEl.textContent = agent.lon.toFixed(6);
        if (hdgEl && !hdgEl.querySelector('input')) hdgEl.innerHTML = `${((agent.heading || 0) * 180 / Math.PI).toFixed(1)}&deg;`;
        if (altEl && !altEl.querySelector('input')) altEl.textContent = `${isUuv ? Math.abs(agent.alt).toFixed(1) : agent.alt.toFixed(1)}m`;
    }

    function hideDetail() {
        document.getElementById('detail-panel').classList.remove('visible');
    }

    function updateSummary() {
        const ids = Object.keys(agents);
        const totalSensors = ids.reduce(
            (sum, id) => sum + (agents[id].sensors || []).length,
            0
        );
        document.getElementById('agent-summary').textContent =
            `${ids.length} agent${ids.length !== 1 ? 's' : ''} | ${totalSensors} sensor${totalSensors !== 1 ? 's' : ''}`;
    }

    function updateStackStatus(agentId, status) {
        if (agents[agentId]) {
            agents[agentId].stack_status = status;
            renderList();
            if (selectedId === agentId) showDetail(agentId);
        }
    }

    function _lowestAvailableNumber() {
        const used = new Set();
        for (const id of Object.keys(agents)) {
            const m = id.match(/_(\d+)$/);
            if (m) used.add(parseInt(m[1], 10));
        }
        let num = 1;
        while (used.has(num)) num++;
        return num;
    }

    function generateId(vehicleType = 'uxv') {
        const prefix = vehicleType.toLowerCase();
        const num = _lowestAvailableNumber();
        return `${prefix}_${String(num).padStart(2, '0')}`;
    }

    function getLastKnownVersion() { return lastKnownVersion; }
    function setLastKnownVersion(v) { lastKnownVersion = v; }

    function getSerializableState() {
        const copy = {};
        for (const [id, a] of Object.entries(agents)) {
            copy[id] = {
                lat: a.lat, lon: a.lon, alt: a.alt, heading: a.heading,
                sensors: [...(a.sensors || [])],
                domain_id: a.domain_id,
                vehicle_type: a.vehicle_type,
                vehicle_class: a.vehicle_class,
                stack_compose_file: a.stack_compose_file,
                stack_env: { ...(a.stack_env || {}) },
                stack_sys_env: { ...(a.stack_sys_env || {}) },
                stack_sys_env_remap: { ...(a.stack_sys_env_remap || {}) },
            };
        }
        return { agents: copy, lastKnownVersion };
    }

    function clear() {
        for (const id of Object.keys(agents)) {
            MapView.removeAgent(id);
        }
        Object.keys(agents).forEach(k => delete agents[k]);
        selectedId = null;
        hideDetail();
        renderList();
        updateSummary();
    }

    return {
        getAll,
        getSelected,
        addAgent,
        removeAgent,
        updateGroundTruth,
        selectAgent,
        updateStackStatus,
        refreshDetail: showDetail,
        generateId,
        renderList,
        setSortMode,
        toggleSortDirection,
        isSortAscending,
        updateSummary,
        clear,
        getLastKnownVersion,
        setLastKnownVersion,
        getSerializableState,
        computeSysEnvValues: _computeSysEnvValues,
    };
})();
