/**
 * Agents module — manages agent state, list UI, selection, and CRUD.
 */

const Agents = (() => {
    const agents = {};  // agent_id -> { lat, lon, alt, heading, sensors, domain_id, vehicle_type, vehicle_class, stack_status }
    let selectedId = null;
    let lastKnownVersion = 0;  // last state_version received from backend
    let sortMode = 'id';  // 'id', 'type', 'domain'

    function getAll() { return agents; }
    function getSelected() { return selectedId; }

    function addAgent(data) {
        const id = data.agent_id;
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
        };

        MapView.addAgent(id, agents[id].lat, agents[id].lon, agents[id].heading);
        renderList();
        updateSummary();
    }

    function removeAgent(agentId) {
        WS.sendBridge({ cmd: 'remove_agent', agent_id: agentId });
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
        let agent = agents[data.agent_id];
        if (!agent) {
            // Auto-create agent from ground truth (e.g. loaded from scenario)
            addAgent({
                agent_id: data.agent_id,
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
        MapView.updateAgent(data.agent_id, data.lat, data.lon, data.heading);
    }

    function selectAgent(agentId) {
        if (selectedId === agentId) {
            // Toggle off if clicking the same agent
            selectedId = null;
            MapView.selectAgent(null);
            hideDetail();
            renderList();
            return;
        }
        selectedId = agentId;
        MapView.selectAgent(agentId);
        renderList();
        showDetail(agentId);
    }

    function setSortMode(mode) {
        sortMode = mode;
        renderList();
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
                    ${a.lat.toFixed(6)}, ${a.lon.toFixed(6)} | ${a.alt.toFixed(1)}m
                </div>
                <div class="agent-sensors">${sensorBadges}</div>
            </div>
        `;
    }

    function renderList() {
        const list = document.getElementById('agent-list');
        const ids = Object.keys(agents).sort();
        document.getElementById('agent-count').textContent = ids.length;

        let html = '';

        if (sortMode === 'type') {
            const typeOrder = ['uav', 'usv', 'ugv', 'uuv', 'uxv'];
            const groups = {};
            for (const id of ids) {
                const vtype = (agents[id].vehicle_type || Icons.getTypeFromId(id)).toLowerCase();
                (groups[vtype] = groups[vtype] || []).push(id);
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
        } else if (sortMode === 'domain') {
            const groups = {};
            for (const id of ids) {
                const d = agents[id].domain_id || 0;
                (groups[d] = groups[d] || []).push(id);
            }
            const domains = Object.keys(groups).map(Number).sort((a, b) => a - b);
            for (const d of domains) {
                html += `<div class="agent-group-header">Domain ${d}</div>`;
                html += groups[d].map(_agentCardHtml).join('');
            }
        } else {
            html = ids.map(_agentCardHtml).join('');
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
        panel.innerHTML = `
            <button class="detail-close" id="detail-close">&times;</button>
            <div class="detail-section">
                <div class="detail-title">
                    <span class="agent-type-icon type-${dvtype}">${Icons.getSvg(dvtype)}</span>
                    Agent: ${agentId}
                </div>
                <div class="form-row">
                    <label class="form-label">Type</label>
                    <span class="form-input" style="border:none; background:none; color:var(--text-primary);">${Icons.getLabel(dvtype)}${agent.vehicle_class ? ' / ' + agent.vehicle_class : ''}</span>
                </div>
                <div class="form-row">
                    <label class="form-label">Domain</label>
                    <span class="form-input" style="border:none; background:none; color:var(--text-primary);">${agent.domain_id}</span>
                </div>
                <div class="form-row">
                    <label class="form-label">Position</label>
                    <span class="form-input" style="border:none; background:none; color:var(--text-primary);">
                        ${agent.lat.toFixed(6)}, ${agent.lon.toFixed(6)}
                    </span>
                </div>
                <div class="form-row">
                    <label class="form-label">Altitude</label>
                    <span class="form-input" style="border:none; background:none; color:var(--text-primary);">${agent.alt.toFixed(1)} m</span>
                </div>
            </div>
            <div class="detail-section">
                <div class="detail-title">Sensors</div>
                <div id="sensor-config-area"></div>
                <button class="btn btn-sm" id="btn-add-sensor" style="margin-top: 8px;">+ Add Sensor</button>
            </div>
            <div class="detail-section">
                <div class="detail-title">Stack</div>
                <div style="margin-bottom: 8px;">
                    <span class="sensor-badge">${agent.stack_status}</span>
                </div>
                <button class="btn btn-sm btn-accent" id="btn-launch-stack">Launch Stack</button>
                <button class="btn btn-sm btn-danger" id="btn-stop-stack" style="margin-left: 4px;">Stop Stack</button>
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
        updateSummary,
        clear,
        getLastKnownVersion,
        setLastKnownVersion,
        getSerializableState,
    };
})();
