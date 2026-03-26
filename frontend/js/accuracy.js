/**
 * Accuracy module — displays pose estimate overlay and error metrics.
 */

const Accuracy = (() => {
    const estimates = {};    // agent_id -> { lat, lon, alt }
    const groundTruth = {};  // agent_id -> { lat, lon, alt }
    const errors = {};       // agent_id -> { horiz_m, vert_m }

    function updateEstimate(data) {
        estimates[data.agent_id] = {
            lat: data.lat,
            lon: data.lon,
            alt: data.alt || 0,
        };
        MapView.updateEstimate(data.agent_id, data.lat, data.lon);
        computeError(data.agent_id);
        renderPanel();
    }

    function updateGroundTruth(data) {
        groundTruth[data.agent_id] = {
            lat: data.lat,
            lon: data.lon,
            alt: data.alt || 0,
        };
        computeError(data.agent_id);
        renderPanel();
    }

    function computeError(agentId) {
        const est = estimates[agentId];
        const gt = groundTruth[agentId];
        if (!est || !gt) return;

        // Haversine horizontal error
        const R = 6371000;
        const dLat = (est.lat - gt.lat) * Math.PI / 180;
        const dLon = (est.lon - gt.lon) * Math.PI / 180;
        const a = Math.sin(dLat / 2) ** 2 +
                  Math.cos(gt.lat * Math.PI / 180) *
                  Math.cos(est.lat * Math.PI / 180) *
                  Math.sin(dLon / 2) ** 2;
        const horizM = R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
        const vertM = Math.abs(est.alt - gt.alt);

        errors[agentId] = { horiz_m: horizM, vert_m: vertM };
    }

    function renderPanel() {
        const panel = document.getElementById('accuracy-panel');
        const ids = Object.keys(errors).sort();

        if (ids.length === 0) {
            panel.classList.remove('visible');
            return;
        }

        panel.classList.add('visible');
        panel.innerHTML = ids.map(id => {
            const e = errors[id];
            const hClass = e.horiz_m > 10 ? 'bad' : e.horiz_m > 3 ? 'warn' : '';
            const vClass = e.vert_m > 10 ? 'bad' : e.vert_m > 5 ? 'warn' : '';
            return `
                <div class="accuracy-item">
                    <span class="accuracy-label">${id}</span>
                    <span class="accuracy-value ${hClass}">H: ${e.horiz_m.toFixed(2)}m</span>
                    <span class="accuracy-value ${vClass}">V: ${e.vert_m.toFixed(2)}m</span>
                </div>
            `;
        }).join('');
    }

    function removeAgent(agentId) {
        delete estimates[agentId];
        delete groundTruth[agentId];
        delete errors[agentId];
        MapView.removeEstimate(agentId);
        renderPanel();
    }

    return {
        updateEstimate,
        updateGroundTruth,
        removeAgent,
    };
})();
