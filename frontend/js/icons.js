/**
 * Icons module — SVG icon strings for vehicle types.
 */

const Icons = (() => {
    const svgs = {
        // Diamond — aerial vehicle
        uav: '<svg viewBox="0 0 24 24"><polygon points="12,2 22,12 12,22 2,12" fill="none" stroke="currentColor" stroke-width="1.5"/><circle cx="12" cy="12" r="2" fill="currentColor"/></svg>',
        // Circle — generic unmanned
        uxv: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-width="1.5"/><circle cx="12" cy="12" r="2" fill="currentColor"/></svg>',
        // Pentagon — surface vessel
        usv: '<svg viewBox="0 0 24 24"><polygon points="12,2 22,9 19,21 5,21 2,9" fill="none" stroke="currentColor" stroke-width="1.5"/><circle cx="12" cy="12" r="2" fill="currentColor"/></svg>',
        // Square — ground vehicle
        ugv: '<svg viewBox="0 0 24 24"><rect x="3" y="3" width="18" height="18" rx="2" fill="none" stroke="currentColor" stroke-width="1.5"/><circle cx="12" cy="12" r="2" fill="currentColor"/></svg>',
        // Inverted triangle — underwater
        uuv: '<svg viewBox="0 0 24 24"><polygon points="3,4 21,4 12,22" fill="none" stroke="currentColor" stroke-width="1.5"/><circle cx="12" cy="11" r="2" fill="currentColor"/></svg>',
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
