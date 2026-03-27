/**
 * Scenario module — handles config load/save via modals.
 */

const Scenario = (() => {
    let modalMode = null;  // 'load' or 'save'

    function init() {
        document.getElementById('btn-load-config').addEventListener('click', showLoad);
        document.getElementById('btn-save-config').addEventListener('click', requestSave);
        document.getElementById('modal-close').addEventListener('click', hideModal);
        document.getElementById('modal-cancel').addEventListener('click', hideModal);
        document.getElementById('modal-confirm').addEventListener('click', confirmModal);

        // Listen for save response
        WS.on('bridge:scenario_saved', (data) => {
            showSaveResult(data.config_yaml);
        });

        // After a successful load, re-fetch state to rebuild the agent list
        WS.on('bridge:info', (data) => {
            if (data.success && data.message && data.message.startsWith('Loaded scenario')) {
                Agents.clear();
                WS.sendBridge({ cmd: 'get_state' });
            }
        });
    }

    function showLoad() {
        modalMode = 'load';
        document.getElementById('modal-title').textContent = 'Load Configuration';
        document.getElementById('config-editor').value = '';
        document.getElementById('config-editor').placeholder = 'Paste YAML configuration here...';
        document.getElementById('modal-confirm').textContent = 'Apply';
        document.getElementById('config-modal').classList.add('visible');
    }

    function requestSave() {
        WS.sendBridge({ cmd: 'save_scenario' });
    }

    function showSaveResult(yaml) {
        modalMode = 'save';
        document.getElementById('modal-title').textContent = 'Save Configuration';
        document.getElementById('config-editor').value = yaml;
        document.getElementById('modal-confirm').textContent = 'Download';
        document.getElementById('config-modal').classList.add('visible');
    }

    function hideModal() {
        document.getElementById('config-modal').classList.remove('visible');
        modalMode = null;
    }

    function confirmModal() {
        const editor = document.getElementById('config-editor');

        if (modalMode === 'load') {
            const yaml = editor.value.trim();
            if (!yaml) {
                App.toast('No configuration provided', 'error');
                return;
            }
            WS.sendBridge({ cmd: 'load_scenario', config_yaml: yaml });
            hideModal();
            App.toast('Loading scenario...', 'info');
        } else if (modalMode === 'save') {
            // Download as file
            const yaml = editor.value;
            const blob = new Blob([yaml], { type: 'text/yaml' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'scenario.yaml';
            a.click();
            URL.revokeObjectURL(url);
            hideModal();
            App.toast('Configuration downloaded', 'success');
        }
    }

    return { init, showLoad, requestSave };
})();
