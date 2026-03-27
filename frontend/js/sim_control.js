/**
 * Sim control module — play, pause, step, reset, speed multiplier, status display.
 *
 * States: READY (at initial conditions), RUNNING, PAUSED (mid-run), COMPLETE
 */

const SimControl = (() => {
    let simTime = 0;
    let simStatus = 'READY';
    let simSpeed = 1.0;
    let simDt = 0.01;

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

        // dt input — commit on Enter or blur
        const dtInput = document.getElementById('sim-dt-input');
        dtInput.addEventListener('change', () => {
            const val = parseFloat(dtInput.value);
            if (val > 0) {
                WS.sendBridge({ cmd: 'set_sim_dt', dt: val });
            }
        });

        // Listen for status updates from backend
        WS.on('bridge:sim_status', (data) => {
            if (data.status) {
                simStatus = data.status;
            }
            if (data.speed !== undefined) {
                simSpeed = data.speed;
            }
            updateStatusDisplay();

            // On reset (READY): update time to 0 and refresh agent positions
            if (simStatus === 'READY') {
                updateTime(0);
                WS.sendBridge({ cmd: 'get_state' });
            }
        });

        // Listen for dt confirmation from backend
        WS.on('bridge:sim_dt', (data) => {
            if (data.success && data.dt !== undefined) {
                simDt = data.dt;
                dtInput.value = simDt;
            }
        });

        updateStatusDisplay();
    }

    function updateTime(timeS) {
        simTime = timeS;
        document.getElementById('sim-time').textContent = `T: ${timeS.toFixed(3)}s`;
    }

    function setStatus(status) {
        if (status) {
            simStatus = status;
            updateStatusDisplay();
        }
    }

    function setDt(dt) {
        if (dt !== undefined && dt > 0) {
            simDt = dt;
            const dtInput = document.getElementById('sim-dt-input');
            if (dtInput) dtInput.value = simDt;
        }
    }

    function updateStatusDisplay() {
        const badge = document.getElementById('sim-status-badge');
        if (badge) {
            badge.textContent = simStatus;
            badge.className = 'sim-status-badge ' + simStatus.toLowerCase();
        }
        // Disable map dragging while sim is running
        MapView.setDraggable(simStatus !== 'RUNNING');
        // dt input only editable in READY state
        const dtInput = document.getElementById('sim-dt-input');
        if (dtInput) dtInput.disabled = (simStatus !== 'READY');
    }

    function getStatus() { return simStatus; }

    return { init, updateTime, setStatus, setDt, getStatus };
})();
