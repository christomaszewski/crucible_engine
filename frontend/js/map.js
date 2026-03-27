/**
 * Map module — Leaflet map, agent markers, pose estimate markers.
 */

const MapView = (() => {
    let map = null;
    const agentMarkers = {};      // agent_id -> L.marker
    const estimateMarkers = {};   // agent_id -> L.marker
    let placeMode = false;
    let placeModeCallback = null;

    // Heading rotation state
    let rotatingAgentId = null;
    let rotatingPendingHeading = null;

    function init() {
        map = L.map('map', {
            center: [38.9072, -77.0369],
            zoom: 15,
            zoomControl: false,
        });

        L.control.zoom({ position: 'bottomright' }).addTo(map);

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

        // --- Heading rotation via right-click drag (delegated) ---
        const mapContainer = document.getElementById('map-container');

        // Suppress context menu on markers only
        mapContainer.addEventListener('contextmenu', (e) => {
            if (e.target.closest('.map-marker')) {
                e.preventDefault();
            }
        });

        // Right-mousedown on a marker starts rotation
        mapContainer.addEventListener('mousedown', (e) => {
            if (e.button !== 2) return;
            const markerEl = e.target.closest('.map-marker');
            if (!markerEl) return;
            const agentId = markerEl.dataset.agent;
            if (!agentId || !agentMarkers[agentId]) return;

            e.preventDefault();
            e.stopPropagation();
            rotatingAgentId = agentId;
            rotatingPendingHeading = null;

            // Disable map and marker dragging during rotation
            map.dragging.disable();
            agentMarkers[agentId].dragging.disable();
            mapContainer.classList.add('rotate-mode');
        });

        // Mousemove computes heading angle from marker center to cursor
        document.addEventListener('mousemove', (e) => {
            if (!rotatingAgentId) return;
            const marker = agentMarkers[rotatingAgentId];
            if (!marker) return;

            const mapEl = document.getElementById('map');
            const mapRect = mapEl.getBoundingClientRect();
            const markerPt = map.latLngToContainerPoint(marker.getLatLng());
            const dx = e.clientX - (mapRect.left + markerPt.x);
            const dy = e.clientY - (mapRect.top + markerPt.y);

            // atan2(dx, -dy): 0 = north (screen up), CW positive
            let angleDeg = Math.atan2(dx, -dy) * 180 / Math.PI;
            if (angleDeg < 0) angleDeg += 360;
            const angleRad = angleDeg * Math.PI / 180;

            // Live visual feedback
            const el = marker.getElement();
            if (el) {
                const shape = el.querySelector('.map-marker-shape');
                if (shape) shape.style.transform = `rotate(${angleDeg}deg)`;
            }

            rotatingPendingHeading = angleRad;
        });

        // Right-mouseup commits the heading
        document.addEventListener('mouseup', (e) => {
            if (!rotatingAgentId || e.button !== 2) return;

            const marker = agentMarkers[rotatingAgentId];
            const agentData = Agents.getAll()[rotatingAgentId] || {};
            const heading = rotatingPendingHeading != null
                ? rotatingPendingHeading
                : (agentData.heading || 0);
            const pos = marker.getLatLng();

            WS.sendBridge({
                cmd: 'set_pose',
                agent_id: rotatingAgentId,
                lat: pos.lat,
                lon: pos.lng,
                alt: agentData.alt || 0,
                heading: heading,
            });

            // Re-enable dragging
            map.dragging.enable();
            if (marker.dragging) marker.dragging.enable();
            mapContainer.classList.remove('rotate-mode');

            rotatingAgentId = null;
            rotatingPendingHeading = null;
        });
    }

    // Marker shape SVGs per vehicle type (outline shapes, 40x40 viewBox)
    // Each shape points "up" (north) at heading=0; CSS rotation handles heading.
    // Heading indicator: a line from center toward the top of the shape.
    const headingLine = '<line class="heading-line" x1="20" y1="20" x2="20" y2="4" />';
    const markerShapes = {
        // Diamond — aerial
        uav: `<polygon points="20,2 38,20 20,38 2,20" />${headingLine}`,
        // Circle — generic
        uxv: `<circle cx="20" cy="20" r="17" />${headingLine}`,
        // Pentagon — surface vessel
        usv: `<polygon points="20,2 37,14 31,36 9,36 3,14" />${headingLine}`,
        // Square — ground vehicle
        ugv: `<rect x="4" y="4" width="32" height="32" rx="3" />${headingLine}`,
        // Triangle — underwater (point = bow, points north at heading 0)
        uuv: `<polygon points="20,2 36,34 4,34" />${headingLine}`,
    };

    function _headingToDeg(radians) {
        // heading: 0 = north, CW positive (radians) → CSS degrees
        return (radians * 180 / Math.PI);
    }

    function createAgentIcon(agentId, selected = false, heading = 0) {
        const vtype = Icons.getTypeFromId(agentId);
        const shape = markerShapes[vtype] || markerShapes.uxv;
        const selClass = selected ? 'selected' : '';
        const deg = _headingToDeg(heading);
        return L.divIcon({
            className: '',
            html: `<div class="map-marker type-${vtype} ${selClass}" data-agent="${agentId}">
                <svg class="map-marker-shape" viewBox="0 0 40 40" style="transform: rotate(${deg}deg)">${shape}</svg>
                <span class="map-marker-label">${agentId}</span>
            </div>`,
            iconSize: [60, 46],
            iconAnchor: [30, 23],
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

    function addAgent(agentId, lat, lon, heading = 0) {
        if (agentMarkers[agentId]) {
            updateAgent(agentId, lat, lon, heading);
            return;
        }

        const marker = L.marker([lat, lon], {
            icon: createAgentIcon(agentId, false, heading),
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

        // Rotate shape via DOM (avoids recreating the icon on every GT update)
        const el = marker.getElement();
        if (el) {
            const shape = el.querySelector('.map-marker-shape');
            if (shape) {
                shape.style.transform = `rotate(${_headingToDeg(heading)}deg)`;
            }
        }
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
        // Update all marker icons (preserve heading)
        for (const [aid, marker] of Object.entries(agentMarkers)) {
            const agentData = Agents.getAll()[aid] || {};
            marker.setIcon(createAgentIcon(aid, aid === agentId, agentData.heading || 0));
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

    function setDraggable(enabled) {
        for (const marker of Object.values(agentMarkers)) {
            if (enabled) {
                marker.dragging.enable();
            } else {
                marker.dragging.disable();
            }
        }
    }

    const hiddenTypes = new Set();

    function setTypeFilter(vehicleType, visible) {
        if (visible) {
            hiddenTypes.delete(vehicleType);
        } else {
            hiddenTypes.add(vehicleType);
        }
        for (const [aid, marker] of Object.entries(agentMarkers)) {
            const vtype = Icons.getTypeFromId(aid);
            const el = marker.getElement();
            if (el) {
                el.style.display = hiddenTypes.has(vtype) ? 'none' : '';
            }
        }
        // Also hide/show estimate markers
        for (const [aid, marker] of Object.entries(estimateMarkers)) {
            const vtype = Icons.getTypeFromId(aid);
            const el = marker.getElement();
            if (el) {
                el.style.display = hiddenTypes.has(vtype) ? 'none' : '';
            }
        }
    }

    function isTypeHidden(vehicleType) {
        return hiddenTypes.has(vehicleType);
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
        setDraggable,
        setTypeFilter,
        isTypeHidden,
        getMap,
    };
})();
