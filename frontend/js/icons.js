/**
 * Icons module — SVG icon strings for vehicle types.
 */

const Icons = (() => {
    const svgs = {
        uxv: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="6" fill="none" stroke="currentColor" stroke-width="1.5"/><circle cx="12" cy="12" r="2" fill="currentColor"/></svg>',
        uav: '<svg viewBox="0 0 24 24"><path d="M12 6l-6 4h4v4H6l6 4 6-4h-4v-4h4z" fill="currentColor"/></svg>',
        usv: '<svg viewBox="0 0 24 24"><path d="M4 14c2-2 4 0 6-2s4 0 6-2" fill="none" stroke="currentColor" stroke-width="1.5"/><path d="M8 14v-4l4-3 4 3v4" fill="none" stroke="currentColor" stroke-width="1.5"/></svg>',
        ugv: '<svg viewBox="0 0 24 24"><rect x="5" y="8" width="14" height="6" rx="1" fill="none" stroke="currentColor" stroke-width="1.5"/><circle cx="8" cy="16" r="2" fill="currentColor"/><circle cx="16" cy="16" r="2" fill="currentColor"/></svg>',
        uuv: '<svg viewBox="0 0 24 24"><ellipse cx="12" cy="12" rx="8" ry="4" fill="none" stroke="currentColor" stroke-width="1.5"/><line x1="20" y1="12" x2="22" y2="10" stroke="currentColor" stroke-width="1.5"/><circle cx="8" cy="12" r="1" fill="currentColor"/></svg>',
    };

    const typeLabels = {
        uxv: 'UxV',
        uav: 'UAV',
        usv: 'USV',
        ugv: 'UGV',
        uuv: 'UUV',
    };

    function getSvg(vehicleType) {
        return svgs[(vehicleType || 'uxv').toLowerCase()] || svgs.uxv;
    }

    function getLabel(vehicleType) {
        return typeLabels[(vehicleType || 'uxv').toLowerCase()] || 'UxV';
    }

    function getTypeFromId(agentId) {
        const match = agentId.match(/^([a-z]+)_/);
        return match ? match[1] : 'uxv';
    }

    return { getSvg, getLabel, getTypeFromId };
})();
