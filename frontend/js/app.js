/**
 * App — main entry point. Initializes all modules and wires up events.
 */

const App = (() => {
    function init() {
        // Initialize map
        MapView.init();

        // Initialize modules
        SimControl.init();
        Scenario.init();
        Orchestrator.init();

        // Connect WebSockets
        WS.connectBridge();
        WS.connectOrchestrator();

        // Wire up WS status indicator
        WS.on('bridge:connected', () => {
            document.getElementById('ws-status').classList.remove('disconnected');
            document.getElementById('ws-status-text').textContent = 'Connected';
        });

        WS.on('bridge:disconnected', () => {
            document.getElementById('ws-status').classList.add('disconnected');
            document.getElementById('ws-status-text').textContent = 'Disconnected';
        });

        // Handle incoming messages
        WS.on('bridge:ground_truth', (data) => {
            Agents.updateGroundTruth(data);
            Accuracy.updateGroundTruth(data);
        });

        WS.on('bridge:sim_clock', (data) => {
            SimControl.updateTime(data.sim_time || 0);
        });

        WS.on('bridge:pose_estimate', (data) => {
            Accuracy.updateEstimate(data);
        });

        WS.on('bridge:state', (data) => {
            const backendVersion = data.state_version || 0;
            const uiVersion = Agents.getLastKnownVersion();
            const uiAgents = Agents.getAll();
            const hasUiAgents = Object.keys(uiAgents).length > 0;

            if (hasUiAgents && uiVersion > backendVersion) {
                // Backend restarted with stale state — push UI state
                const state = Agents.getSerializableState();
                WS.sendBridge({
                    cmd: 'push_state',
                    agents: state.agents,
                    state_version: state.lastKnownVersion,
                });
                toast('Backend restart detected — restoring state from UI', 'info');
            } else {
                // Accept backend state
                if (data.data && data.data.agents) {
                    if (backendVersion > uiVersion) {
                        Agents.clear();
                    }
                    for (const [id, agentData] of Object.entries(data.data.agents)) {
                        const existing = Agents.getAll()[id];
                        if (!existing) {
                            Agents.addAgent({
                                agent_id: id,
                                ...agentData,
                            });
                        } else {
                            // Merge all data into existing agent
                            if (agentData.lat !== undefined) existing.lat = agentData.lat;
                            if (agentData.lon !== undefined) existing.lon = agentData.lon;
                            if (agentData.alt !== undefined) existing.alt = agentData.alt;
                            if (agentData.heading !== undefined) existing.heading = agentData.heading;
                            if (agentData.sensors) existing.sensors = agentData.sensors;
                            if (agentData.sensor_configs) existing.sensor_configs = agentData.sensor_configs;
                            if (agentData.vehicle_type) existing.vehicle_type = agentData.vehicle_type;
                            if (agentData.vehicle_class) existing.vehicle_class = agentData.vehicle_class;
                            if (agentData.domain_id !== undefined) existing.domain_id = agentData.domain_id;
                            // Update map marker position
                            MapView.updateAgent(id, existing.lat, existing.lon, existing.heading);
                        }
                    }
                    Agents.renderList();
                    Agents.updateSummary();
                    // Refresh detail panel if open (sensor configs may have arrived)
                    const sel = Agents.getSelected();
                    if (sel && Agents.getAll()[sel]) Agents.refreshDetail(sel);
                    SimControl.updateTime(data.data.sim_time_s || 0);
                    if (data.data.status) SimControl.setStatus(data.data.status);
                    if (data.data.sim_dt) SimControl.setDt(data.data.sim_dt);
                    MapView.fitAgents();
                    updatePlaceButton();
                }
                Agents.setLastKnownVersion(backendVersion);
            }
        });

        WS.on('bridge:info', (data) => {
            if (data.state_version !== undefined) {
                Agents.setLastKnownVersion(data.state_version);
            }
            if (data.success) {
                toast(data.message, 'success');
            } else {
                toast(data.message, 'error');
            }
        });

        WS.on('bridge:error', (data) => {
            toast(data.message, 'error');
        });

        // Toolbar buttons
        document.getElementById('btn-add-agent').addEventListener('click', showAddAgentModal);
        document.getElementById('btn-fit-agents').addEventListener('click', () => MapView.fitAgents());

        // Agent list sort
        document.getElementById('agent-sort').addEventListener('change', (e) => {
            Agents.setSortMode(e.target.value);
        });

        document.getElementById('sort-dir-btn').addEventListener('click', () => {
            Agents.toggleSortDirection();
            document.getElementById('sort-dir-btn').innerHTML =
                Agents.isSortAscending() ? '&#9650;' : '&#9660;';
        });

        // Map type filter checkboxes
        document.querySelectorAll('#map-filter input[type="checkbox"]').forEach(cb => {
            cb.addEventListener('change', () => {
                MapView.setTypeFilter(cb.dataset.type, cb.checked);
            });
        });

        // Place split button
        initPlaceButton();

        // Add agent modal
        document.getElementById('add-agent-close').addEventListener('click', hideAddAgentModal);
        document.getElementById('add-agent-cancel').addEventListener('click', hideAddAgentModal);
        document.getElementById('add-agent-confirm').addEventListener('click', confirmAddAgent);
    }

    // -- Add agent via modal ------------------------------------------------

    function showAddAgentModal() {
        const typeSelect = document.getElementById('new-agent-type');
        const updateIdAndDomain = () => {
            const id = Agents.generateId(typeSelect.value);
            document.getElementById('new-agent-id').value = id;
            // Extract number from generated ID and use as domain_id
            const match = id.match(/_(\d+)$/);
            if (match) {
                document.getElementById('new-agent-domain').value = parseInt(match[1], 10);
            }
        };
        typeSelect.onchange = updateIdAndDomain;
        updateIdAndDomain();
        document.getElementById('new-agent-class').value = '';
        document.getElementById('add-agent-modal').classList.add('visible');
    }

    function hideAddAgentModal() {
        document.getElementById('add-agent-modal').classList.remove('visible');
    }

    function confirmAddAgent() {
        const agentId = document.getElementById('new-agent-id').value.trim();
        const lat = parseFloat(document.getElementById('new-agent-lat').value);
        const lon = parseFloat(document.getElementById('new-agent-lon').value);
        const alt = parseFloat(document.getElementById('new-agent-alt').value);
        const heading = parseFloat(document.getElementById('new-agent-heading').value);
        const domainId = parseInt(document.getElementById('new-agent-domain').value, 10);
        const vehicleType = document.getElementById('new-agent-type').value;
        const vehicleClass = document.getElementById('new-agent-class').value.trim();

        if (!agentId) {
            toast('Agent ID is required', 'error');
            return;
        }

        WS.sendBridge({
            cmd: 'add_agent',
            agent_id: agentId,
            lat, lon, alt, heading,
            domain_id: domainId,
            vehicle_type: vehicleType,
            vehicle_class: vehicleClass,
        });

        // Optimistically add to UI so marker appears immediately
        Agents.addAgent({
            agent_id: agentId,
            lat, lon, alt, heading,
            sensors: [],
            domain_id: domainId,
            vehicle_type: vehicleType,
            vehicle_class: vehicleClass,
        });
        updatePlaceButton();

        hideAddAgentModal();
    }

    // -- Place agent on map -------------------------------------------------

    let placeVehicleType = 'uxv';

    function initPlaceButton() {
        const mainBtn = document.getElementById('btn-place-agent');
        const arrowBtn = document.getElementById('btn-place-dropdown');
        const menu = document.getElementById('place-menu');

        // Set initial icon
        updatePlaceButton();

        mainBtn.addEventListener('click', enterPlaceMode);

        arrowBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            menu.classList.toggle('visible');
        });

        // Menu item selection
        menu.querySelectorAll('.split-btn-item').forEach(item => {
            item.addEventListener('click', () => {
                placeVehicleType = item.dataset.type;
                updatePlaceButton();
                menu.classList.remove('visible');
            });
        });

        // Close menu on outside click
        document.addEventListener('click', () => {
            menu.classList.remove('visible');
        });
    }

    function updatePlaceButton() {
        const nextId = Agents.generateId(placeVehicleType);
        document.getElementById('place-icon').innerHTML = Icons.getSvg(placeVehicleType);
        document.getElementById('place-label').textContent = `Place ${nextId}`;

        // Highlight active item in menu
        document.querySelectorAll('#place-menu .split-btn-item').forEach(item => {
            item.classList.toggle('active', item.dataset.type === placeVehicleType);
        });
    }

    function enterPlaceMode() {
        MapView.enterPlaceMode((lat, lon) => {
            const agentId = Agents.generateId(placeVehicleType);
            const match = agentId.match(/_(\d+)$/);
            const domainId = match ? parseInt(match[1], 10) : 0;
            WS.sendBridge({
                cmd: 'add_agent',
                agent_id: agentId,
                lat, lon,
                alt: 100.0,
                heading: 0,
                domain_id: domainId,
                vehicle_type: placeVehicleType,
                vehicle_class: '',
            });

            // Optimistically add to UI so marker appears immediately
            Agents.addAgent({
                agent_id: agentId,
                lat, lon,
                alt: 100.0,
                heading: 0,
                sensors: [],
                domain_id: domainId,
                vehicle_type: placeVehicleType,
                vehicle_class: '',
            });
            updatePlaceButton();
        });
    }

    // -- Toast notifications ------------------------------------------------

    function toast(message, type = 'info') {
        const container = document.getElementById('toast-container');
        const el = document.createElement('div');
        el.className = `toast ${type}`;
        el.textContent = message;
        container.appendChild(el);

        setTimeout(() => {
            el.style.opacity = '0';
            el.style.transform = 'translateX(20px)';
            el.style.transition = 'all 200ms ease';
            setTimeout(() => el.remove(), 200);
        }, 3000);
    }

    function updateHotkeyOverlay() {
        const overlay = document.getElementById('hotkey-overlay');
        const selectedId = Agents.getSelected();
        if (!selectedId) {
            overlay.classList.remove('visible');
            return;
        }
        const agentData = Agents.getAll()[selectedId] || {};
        const vtype = (agentData.vehicle_type || Icons.getTypeFromId(selectedId)).toLowerCase();

        let lines = [
            '<kbd>R</kbd> Set heading',
        ];
        if (vtype === 'uuv') {
            lines.push('<kbd>A</kbd> Set depth');
        } else if (vtype !== 'ugv' && vtype !== 'usv') {
            lines.push('<kbd>A</kbd> Set altitude');
        }
        lines.push('<kbd>ESC</kbd> Cancel / deselect');
        overlay.innerHTML = lines.join('<br>');
        overlay.classList.add('visible');
    }

    return { init, toast, updatePlaceButton, updateHotkeyOverlay };
})();

// Boot
document.addEventListener('DOMContentLoaded', () => App.init());
