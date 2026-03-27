/**
 * Sim control module — play, pause, step, reset, speed multiplier, status display.
 */

const SimControl = (() => {
    let simTime = 0;
    let simStatus = 'PAUSED';
    let simSpeed = 1.0;

    function init() {
        document.getElementById('btn-play').addEventListener('click', () => {
            WS.sendBridge({ cmd: 'sim_control', action: 'resume' });
        });

        document.getElementById('btn-pause').addEventListener('click', () => {
            WS.sendBridge({ cmd: 'sim_control', action: 'pause' });
        });

        document.getElementById('btn-step').addEventListener('click', () => {
            WS.sendBridge({ cmd: 'sim_control', action: 'step' });
        });

        document.getElementById('btn-reset').addEventListener('click', () => {
            WS.sendBridge({ cmd: 'sim_control', action: 'reset' });
        });

        document.getElementById('speed-select').addEventListener('change', (e) => {
            const multiplier = parseFloat(e.target.value);
            WS.sendBridge({ cmd: 'set_speed', multiplier });
        });

        // Listen for status updates from backend
        WS.on('bridge:sim_status', (data) => {
            const wasReset = data.status === 'PAUSED' && data.message && data.message.includes('reset');
            if (data.status) {
                simStatus = data.status;
            }
            if (data.speed !== undefined) {
                simSpeed = data.speed;
            }
            updateStatusDisplay();

            // On reset: update time to 0 and refresh agent positions
            if (wasReset) {
                updateTime(0);
                WS.sendBridge({ cmd: 'get_state' });
            }
        });

        updateStatusDisplay();
    }

    function updateTime(timeS) {
        simTime = timeS;
        document.getElementById('sim-time').textContent = `T: ${timeS.toFixed(3)}s`;
    }

    function updateStatusDisplay() {
        const badge = document.getElementById('sim-status-badge');
        if (badge) {
            badge.textContent = simStatus;
            badge.className = 'sim-status-badge ' + simStatus.toLowerCase();
        }
        // Disable map dragging while sim is running
        MapView.setDraggable(simStatus !== 'RUNNING');
    }

    return { init, updateTime };
})();
