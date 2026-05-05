/**
 * Map module — Leaflet map, agent markers, pose estimate markers.
 */

const MapView = (() => {
    let map = null;
    const agentMarkers = {};      // agent_name -> L.marker
    const estimateMarkers = {};   // agent_name -> L.marker
    let placeMode = false;
    let placeModeCallback = null;

    // Adjustment mode: null, 'heading', or 'altitude'
    let adjustMode = null;
    let adjustAgentId = null;
    let adjustPendingValue = null;
    let adjustStartAlt = 0;
    let adjustStartY = 0;

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

        // Click handler for place mode OR commit adjustment
        map.on('click', (e) => {
            if (adjustMode) {
                _commitAdjustment();
                return;
            }
            if (placeMode && placeModeCallback) {
                placeModeCallback(e.latlng.lat, e.latlng.lng);
                exitPlaceMode();
            }
        });

        const mapContainer = document.getElementById('map-container');
        const banner = document.getElementById('adjust-banner');

        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            // ESC cancels any active mode
            if (e.key === 'Escape') {
                if (adjustMode) {
                    _cancelAdjustment();
                    return;
                }
                if (placeMode) {
                    exitPlaceMode();
                    return;
                }
            }

            // Ignore hotkeys when typing in an input
            if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT') return;

            const selectedId = Agents.getSelected();
            if (!selectedId || !agentMarkers[selectedId]) return;

            if (e.key === 'r' || e.key === 'R') {
                e.preventDefault();
                _enterAdjustMode('heading', selectedId);
            } else if (e.key === 'a' || e.key === 'A') {
                const agentData = Agents.getAll()[selectedId] || {};
                const vtype = (agentData.vehicle_type || Icons.getTypeFromId(selectedId)).toLowerCase();
                if (vtype === 'ugv' || vtype === 'usv') return; // no altitude adjust for ground/surface
                e.preventDefault();
                _enterAdjustMode(vtype === 'uuv' ? 'depth' : 'altitude', selectedId);
            }
        });

        // Mousemove for live adjustment feedback
        document.addEventListener('mousemove', (e) => {
            if (!adjustMode || !adjustAgentId) return;
            const marker = agentMarkers[adjustAgentId];
            if (!marker) return;

            if (adjustMode === 'heading') {
                const mapEl = document.getElementById('map');
                const mapRect = mapEl.getBoundingClientRect();
                const markerPt = map.latLngToContainerPoint(marker.getLatLng());
                const dx = e.clientX - (mapRect.left + markerPt.x);
                const dy = e.clientY - (mapRect.top + markerPt.y);

                let angleDeg = Math.atan2(dx, -dy) * 180 / Math.PI;
                if (angleDeg < 0) angleDeg += 360;

                // Live rotation
                const el = marker.getElement();
                if (el) {
                    const shape = el.querySelector('.map-marker-shape');
                    if (shape) shape.style.transform = `rotate(${angleDeg}deg)`;
                }

                adjustPendingValue = angleDeg * Math.PI / 180;
                banner.textContent = `Heading: ${angleDeg.toFixed(1)}° — click to set, ESC to cancel`;
            } else if (adjustMode === 'altitude' || adjustMode === 'depth') {
                const deltaY = adjustStartY - e.clientY; // up = positive
                const scale = adjustMode === 'depth' ? -0.5 : 0.5;
                let newAlt = adjustStartAlt + deltaY * scale;
                if (adjustMode === 'altitude') newAlt = Math.max(0, newAlt);
                if (adjustMode === 'depth') newAlt = Math.min(0, newAlt);
                adjustPendingValue = newAlt;
                const label = adjustMode === 'depth' ? 'Depth' : 'Alt';
                const displayVal = adjustMode === 'depth' ? Math.abs(newAlt).toFixed(1) : newAlt.toFixed(1);
                banner.textContent = `${label}: ${displayVal}m — click to set, ESC to cancel`;

                // Visual indicator near marker
                const el = marker.getElement();
                if (el) {
                    let ind = el.querySelector('.altitude-indicator');
                    if (!ind) {
                        ind = document.createElement('div');
                        ind.className = 'altitude-indicator';
                        el.querySelector('.map-marker').appendChild(ind);
                    }
                    ind.textContent = `${label}: ${displayVal}m`;
                }
            }
        });
    }

    function _enterAdjustMode(mode, agentId) {
        // Cancel any existing adjustment
        if (adjustMode) _cancelAdjustment();

        adjustMode = mode;
        adjustAgentId = agentId;
        adjustPendingValue = null;

        const mapContainer = document.getElementById('map-container');
        const banner = document.getElementById('adjust-banner');
        const marker = agentMarkers[agentId];

        // Disable map panning and marker dragging
        map.dragging.disable();
        if (marker) marker.dragging.disable();
        mapContainer.classList.add('adjust-mode');

        if (mode === 'heading') {
            banner.textContent = `Move mouse around ${agentId} to set heading — click to set, ESC to cancel`;
        } else if (mode === 'altitude' || mode === 'depth') {
            const agentData = Agents.getAll()[agentId] || {};
            adjustStartAlt = agentData.alt || 0;
            adjustStartY = null;
            const captureStart = (e) => {
                if (adjustStartY === null) adjustStartY = e.clientY;
            };
            document.addEventListener('mousemove', captureStart, { once: true });
            const label = mode === 'depth' ? 'depth' : 'altitude';
            const displayVal = mode === 'depth' ? Math.abs(adjustStartAlt).toFixed(1) : adjustStartAlt.toFixed(1);
            banner.textContent = `Move mouse up/down to adjust ${agentId} ${label} (${displayVal}m) — click to set, ESC to cancel`;
        }

        banner.classList.add('visible');
    }

    function _commitAdjustment() {
        if (!adjustMode || !adjustAgentId) return;

        const marker = agentMarkers[adjustAgentId];
        const agentData = Agents.getAll()[adjustAgentId] || {};
        const pos = marker.getLatLng();
        const commitId = adjustAgentId;

        if (adjustMode === 'heading' && adjustPendingValue != null) {
            agentData.heading = adjustPendingValue;
            WS.sendBridge({
                cmd: 'set_pose',
                agent_name: adjustAgentId,
                lat: pos.lat,
                lon: pos.lng,
                alt: agentData.alt || 0,
                heading: adjustPendingValue,
            });
        } else if ((adjustMode === 'altitude' || adjustMode === 'depth') && adjustPendingValue != null) {
            agentData.alt = adjustPendingValue;
            WS.sendBridge({
                cmd: 'set_pose',
                agent_name: adjustAgentId,
                lat: pos.lat,
                lon: pos.lng,
                alt: adjustPendingValue,
                heading: agentData.heading || 0,
            });
        }

        _exitAdjustMode();

        // Refresh detail panel and list to reflect new values
        if (Agents.getSelected() === commitId) Agents.refreshDetail(commitId);
        Agents.renderList();
    }

    function _cancelAdjustment() {
        // Revert visual heading to actual value
        if (adjustMode === 'heading' && adjustAgentId) {
            const marker = agentMarkers[adjustAgentId];
            const agentData = Agents.getAll()[adjustAgentId] || {};
            if (marker) {
                const el = marker.getElement();
                if (el) {
                    const shape = el.querySelector('.map-marker-shape');
                    if (shape) shape.style.transform = `rotate(${_headingToDeg(agentData.heading || 0)}deg)`;
                }
            }
        }
        _exitAdjustMode();
    }

    function _exitAdjustMode() {
        if (adjustAgentId) {
            const marker = agentMarkers[adjustAgentId];
            if (marker) {
                if (marker.dragging) marker.dragging.enable();
                // Remove altitude/depth indicator
                const el = marker.getElement();
                if (el) {
                    const ind = el.querySelector('.altitude-indicator');
                    if (ind) ind.remove();
                }
            }
        }
        map.dragging.enable();
        document.getElementById('map-container').classList.remove('adjust-mode');
        document.getElementById('adjust-banner').classList.remove('visible');
        adjustMode = null;
        adjustAgentId = null;
        adjustPendingValue = null;
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
                agent_name: agentId,
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

    function zoomToAgent(agentId, zoomLevel = 17) {
        const marker = agentMarkers[agentId];
        if (!marker) return false;
        map.flyTo(marker.getLatLng(), zoomLevel, { duration: 0.6 });
        return true;
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
        zoomToAgent,
        setDraggable,
        setTypeFilter,
        isTypeHidden,
        getMap,
    };
})();
