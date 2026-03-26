/**
 * WebSocket client — manages connections to the bridge and orchestrator.
 */

const WS = (() => {
    let bridgeWs = null;
    let orchWs = null;
    const listeners = {};
    let reconnectTimer = null;

    function getWsUrl(path) {
        const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
        return `${proto}//${location.host}${path}`;
    }

    function connectBridge() {
        if (bridgeWs && bridgeWs.readyState === WebSocket.OPEN) return;

        const url = getWsUrl('/ws/bridge');
        bridgeWs = new WebSocket(url);

        bridgeWs.onopen = () => {
            console.log('[WS] Bridge connected');
            emit('bridge:connected');
            if (reconnectTimer) {
                clearTimeout(reconnectTimer);
                reconnectTimer = null;
            }
            // Request current state on connect
            sendBridge({ cmd: 'get_state' });
        };

        bridgeWs.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                emit('bridge:message', data);
                if (data.type) {
                    emit(`bridge:${data.type}`, data);
                }
            } catch (e) {
                console.error('[WS] Parse error:', e);
            }
        };

        bridgeWs.onclose = () => {
            console.log('[WS] Bridge disconnected');
            emit('bridge:disconnected');
            scheduleReconnect();
        };

        bridgeWs.onerror = (err) => {
            console.error('[WS] Bridge error:', err);
        };
    }

    function connectOrchestrator() {
        if (orchWs && orchWs.readyState === WebSocket.OPEN) return;

        const url = getWsUrl('/ws/orchestrator');
        orchWs = new WebSocket(url);

        orchWs.onopen = () => {
            console.log('[WS] Orchestrator connected');
            emit('orch:connected');
        };

        orchWs.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                emit('orch:message', data);
                if (data.type) {
                    emit(`orch:${data.type}`, data);
                }
            } catch (e) {
                console.error('[WS] Orchestrator parse error:', e);
            }
        };

        orchWs.onclose = () => {
            console.log('[WS] Orchestrator disconnected');
            emit('orch:disconnected');
        };
    }

    function scheduleReconnect() {
        if (reconnectTimer) return;
        reconnectTimer = setTimeout(() => {
            reconnectTimer = null;
            connectBridge();
        }, 3000);
    }

    function sendBridge(data) {
        if (bridgeWs && bridgeWs.readyState === WebSocket.OPEN) {
            bridgeWs.send(JSON.stringify(data));
        } else {
            console.warn('[WS] Bridge not connected, dropping message:', data);
        }
    }

    function sendOrch(data) {
        if (orchWs && orchWs.readyState === WebSocket.OPEN) {
            orchWs.send(JSON.stringify(data));
        } else {
            console.warn('[WS] Orchestrator not connected, dropping message:', data);
        }
    }

    function on(event, callback) {
        if (!listeners[event]) listeners[event] = [];
        listeners[event].push(callback);
    }

    function off(event, callback) {
        if (!listeners[event]) return;
        listeners[event] = listeners[event].filter(cb => cb !== callback);
    }

    function emit(event, data) {
        if (!listeners[event]) return;
        for (const cb of listeners[event]) {
            try { cb(data); } catch (e) { console.error('[WS] Listener error:', e); }
        }
    }

    function isBridgeConnected() {
        return bridgeWs && bridgeWs.readyState === WebSocket.OPEN;
    }

    return {
        connectBridge,
        connectOrchestrator,
        sendBridge,
        sendOrch,
        on,
        off,
        isBridgeConnected,
    };
})();
