/**
 * Sim control module — play, pause, step, speed multiplier.
 */

const SimControl = (() => {
    let simTime = 0;

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

        document.getElementById('speed-select').addEventListener('change', (e) => {
            const multiplier = parseFloat(e.target.value);
            WS.sendBridge({ cmd: 'set_speed', multiplier });
        });
    }

    function updateTime(timeS) {
        simTime = timeS;
        document.getElementById('sim-time').textContent = `T: ${timeS.toFixed(3)}s`;
    }

    return { init, updateTime };
})();
