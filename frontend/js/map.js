/**
 * Map module — Leaflet map, agent markers, pose estimate markers.
 */

const MapView = (() => {
    let map = null;
    const agentMarkers = {};      // agent_id -> L.marker
    const estimateMarkers = {};   // agent_id -> L.marker
    let placeMode = false;
    let placeModeCallback = null;

    function init() {
        map = L.map('map', {
            center: [38.9072, -77.0369],
            zoom: 15,
            zoomControl: true,
        });

        // Dark tile layer
        L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
            attribution: '&copy; OpenStreetMap &copy; CARTO',
            maxZoom: 20,
        }).addTo(map);

        // Click handler for place mode
        map.on('click', (e) => {
            if (placeMode && placeModeCallback) {
                placeModeCallback(e.latlng.lat, e.latlng.lng);
                exitPlaceMode();
            }
        });

        // ESC to cancel place mode
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && placeMode) {
                exitPlaceMode();
            }
        });
    }

    function createAgentIcon(agentId, selected = false) {
        const vtype = Icons.getTypeFromId(agentId);
        const svg = Icons.getSvg(vtype);
        const selClass = selected ? 'selected' : '';
        return L.divIcon({
            className: '',
            html: `<div class="agent-marker type-${vtype} ${selClass}">${svg}</div>`,
            iconSize: [28, 28],
            iconAnchor: [14, 14],
        });
    }

    function createEstimateIcon() {
        return L.divIcon({
            className: '',
            html: '<div class="estimate-marker"></div>',
            iconSize: [28, 28],
            iconAnchor: [14, 14],
        });
    }

    function addAgent(agentId, lat, lon) {
        if (agentMarkers[agentId]) {
            agentMarkers[agentId].setLatLng([lat, lon]);
            return;
        }

        const marker = L.marker([lat, lon], {
            icon: createAgentIcon(agentId),
            draggable: true,
            title: agentId,
        }).addTo(map);

        marker.on('click', () => {
            Agents.selectAgent(agentId);
        });

        marker.on('dragend', () => {
            const pos = marker.getLatLng();
            const agentData = Agents.getAll()[agentId] || {};
            WS.sendBridge({
                cmd: 'set_pose',
                agent_id: agentId,
                lat: pos.lat,
                lon: pos.lng,
                alt: agentData.alt || 0,
                heading: agentData.heading || 0,
            });
        });

        agentMarkers[agentId] = marker;
    }

    function updateAgent(agentId, lat, lon, heading) {
        const marker = agentMarkers[agentId];
        if (!marker) return;
        marker.setLatLng([lat, lon]);
    }

    function removeAgent(agentId) {
        const marker = agentMarkers[agentId];
        if (marker) {
            map.removeLayer(marker);
            delete agentMarkers[agentId];
        }
        removeEstimate(agentId);
    }

    function selectAgent(agentId) {
        // Update all marker icons
        for (const [aid, marker] of Object.entries(agentMarkers)) {
            marker.setIcon(createAgentIcon(aid, aid === agentId));
        }
    }

    function updateEstimate(agentId, lat, lon) {
        if (!estimateMarkers[agentId]) {
            estimateMarkers[agentId] = L.marker([lat, lon], {
                icon: createEstimateIcon(),
                interactive: false,
            }).addTo(map);
        } else {
            estimateMarkers[agentId].setLatLng([lat, lon]);
        }
    }

    function removeEstimate(agentId) {
        const marker = estimateMarkers[agentId];
        if (marker) {
            map.removeLayer(marker);
            delete estimateMarkers[agentId];
        }
    }

    function enterPlaceMode(callback) {
        placeMode = true;
        placeModeCallback = callback;
        document.getElementById('map-container').classList.add('place-mode');
        document.getElementById('place-banner').classList.add('visible');
    }

    function exitPlaceMode() {
        placeMode = false;
        placeModeCallback = null;
        document.getElementById('map-container').classList.remove('place-mode');
        document.getElementById('place-banner').classList.remove('visible');
    }

    function fitAgents() {
        const markers = Object.values(agentMarkers);
        if (markers.length === 0) return;
        if (markers.length === 1) {
            map.setView(markers[0].getLatLng(), 16);
            return;
        }
        const group = L.featureGroup(markers);
        map.fitBounds(group.getBounds().pad(0.2));
    }

    function getMap() { return map; }

    return {
        init,
        addAgent,
        updateAgent,
        removeAgent,
        selectAgent,
        updateEstimate,
        removeEstimate,
        enterPlaceMode,
        exitPlaceMode,
        fitAgents,
        getMap,
    };
})();
