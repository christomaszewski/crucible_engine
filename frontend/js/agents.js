/**
 * Agents module — manages agent state, list UI, selection, and CRUD.
 */

const Agents = (() => {
    const agents = {};  // agent_id -> { lat, lon, alt, heading, sensors, domain_id, stack_status }
    let selectedId = null;
    let agentCounter = 1;

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
            domain_id: data.domain_id || 0,
            stack_status: 'STOPPED',
        };

        MapView.addAgent(id, agents[id].lat, agents[id].lon);
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
        selectedId = agentId;
        MapView.selectAgent(agentId);
        renderList();
        showDetail(agentId);
    }

    function renderList() {
        const list = document.getElementById('agent-list');
        const ids = Object.keys(agents).sort();
        document.getElementById('agent-count').textContent = ids.length;

        list.innerHTML = ids.map(id => {
            const a = agents[id];
            const selected = id === selectedId ? 'selected' : '';
            const sensorBadges = (a.sensors || [])
                .map(s => `<span class="sensor-badge">${s}</span>`)
                .join('');
            const statusClass = (a.stack_status || 'STOPPED').toLowerCase();

            return `
                <div class="agent-card ${selected}" data-id="${id}">
                    <div class="agent-card-header">
                        <span class="agent-id">${id}</span>
                        <span class="agent-status ${statusClass}"></span>
                    </div>
                    <div class="agent-meta">
                        ${a.lat.toFixed(6)}, ${a.lon.toFixed(6)} | ${a.alt.toFixed(1)}m
                    </div>
                    <div class="agent-sensors">${sensorBadges}</div>
                </div>
            `;
        }).join('');

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

        panel.innerHTML = `
            <div class="detail-section">
                <div class="detail-title">Agent: ${agentId}</div>
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

    function generateId() {
        const id = `uav_${String(agentCounter).padStart(2, '0')}`;
        agentCounter++;
        return id;
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
        generateId,
        renderList,
        updateSummary,
        clear,
    };
})();
