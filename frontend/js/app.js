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
            SimControl.updateTime(data.sim_time || 0);
        });

        WS.on('bridge:pose_estimate', (data) => {
            Accuracy.updateEstimate(data);
        });

        WS.on('bridge:state', (data) => {
            // Full state update — rebuild agent list
            if (data.data && data.data.agents) {
                for (const [id, agentData] of Object.entries(data.data.agents)) {
                    const existing = Agents.getAll()[id];
                    if (!existing) {
                        Agents.addAgent({
                            agent_id: id,
                            ...agentData,
                        });
                    }
                }
                SimControl.updateTime(data.data.sim_time_s || 0);
            }
        });

        WS.on('bridge:info', (data) => {
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
        document.getElementById('btn-place-agent').addEventListener('click', enterPlaceMode);
        document.getElementById('btn-fit-agents').addEventListener('click', () => MapView.fitAgents());

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

        hideAddAgentModal();
    }

    // -- Place agent on map -------------------------------------------------

    function enterPlaceMode() {
        MapView.enterPlaceMode((lat, lon) => {
            const vehicleType = 'uxv';
            const agentId = Agents.generateId(vehicleType);
            const match = agentId.match(/_(\d+)$/);
            const domainId = match ? parseInt(match[1], 10) : 0;
            WS.sendBridge({
                cmd: 'add_agent',
                agent_id: agentId,
                lat, lon,
                alt: 100.0,
                heading: 0,
                domain_id: domainId,
                vehicle_type: vehicleType,
                vehicle_class: '',
            });
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

    return { init, toast };
})();

// Boot
document.addEventListener('DOMContentLoaded', () => App.init());
