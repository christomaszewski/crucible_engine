/**
 * Orchestrator module — manages agent stack lifecycle from the UI.
 */

const Orchestrator = (() => {
    let stacksHostPath = '';
    let stacksContainerPath = '/opt/stacks';
    let testName = 'test_default';
    let runId = 1;

    function init() {
        WS.on('orch:orch_config', (data) => {
            stacksHostPath = data.stacks_host_path || '';
            stacksContainerPath = data.stacks_container_path || '/opt/stacks';
        });

        WS.on('orch:stack_update', (data) => {
            Agents.updateStackStatus(data.agent_name, data.status, data.services);
            if (data.status === 'RUNNING') {
                App.toast(`Stack for ${data.agent_name} is running`, 'success');
            } else if (data.status === 'DEGRADED') {
                const down = Object.entries(data.services || {})
                    .filter(([, s]) => s !== 'running')
                    .map(([name]) => name);
                const svcList = down.length ? down.join(', ') : 'unknown';
                App.toast(`${data.agent_name}: ${svcList} stopped unexpectedly`, 'warning');
            } else if (data.status === 'ERROR') {
                App.toast(`Stack error for ${data.agent_name}: ${data.error || 'unknown'}`, 'error');
            } else if (data.status === 'STOPPED') {
                App.toast(`Stack for ${data.agent_name} stopped`);
            }
        });

        WS.on('orch:stack_status', (data) => {
            for (const [agentId, info] of Object.entries(data.stacks || {})) {
                Agents.updateStackStatus(agentId, info.status, info.services);
            }
        });

        // Request current stack status on connect/reconnect
        WS.on('orch:connected', () => {
            refreshStatus();
        });
    }

    function launchStack(agentId, silent) {
        const agent = Agents.getAll()[agentId];
        if (!agent) return;

        const composeFile = agent.stack_compose_file || '/opt/stacks/agent_stack.yml';
        if (!composeFile) {
            App.toast(`No compose file set for ${agentId}`, 'error');
            return;
        }

        // Build env: enabled system vars (with optional remapping) + user env
        const sysValues = Agents.computeSysEnvValues(agentId);
        const sysFlags = agent.stack_sys_env || {};
        const remaps = agent.stack_sys_env_remap || {};
        const env = {};
        for (const [key, val] of Object.entries(sysValues)) {
            if (sysFlags[key] !== false) {
                const emitKey = remaps[key] || key;
                env[emitKey] = val;
            }
        }
        Object.assign(env, agent.stack_env || {});

        WS.sendOrch({
            cmd: 'launch_stack',
            agent_name: agentId,
            compose_file: composeFile,
            env,
        });

        Agents.updateStackStatus(agentId, 'STARTING');
        if (!silent) App.toast(`Launching stack for ${agentId}...`, 'info');
    }

    function stopStack(agentId) {
        WS.sendOrch({
            cmd: 'stop_stack',
            agent_name: agentId,
        });

        Agents.updateStackStatus(agentId, 'STOPPING');
        App.toast(`Stopping stack for ${agentId}...`, 'info');
    }

    function launchAllStacks() {
        const all = Agents.getAll();
        let launched = 0;
        for (const [id, agent] of Object.entries(all)) {
            if (agent.stack_compose_file && !['RUNNING', 'STARTING'].includes(agent.stack_status)) {
                launchStack(id, true);
                launched++;
            }
        }
        if (launched === 0) {
            App.toast('No stacks to launch (set compose files first)', 'warning');
        } else {
            App.toast(`Launching ${launched} stack(s)...`, 'info');
        }
    }

    function stopAllStacks() {
        WS.sendOrch({ cmd: 'stop_all_stacks' });
        // Optimistically mark all running/degraded agents as stopping
        const all = Agents.getAll();
        let stopped = 0;
        for (const [id, agent] of Object.entries(all)) {
            if (['RUNNING', 'DEGRADED', 'STARTING'].includes(agent.stack_status)) {
                Agents.updateStackStatus(id, 'STOPPING');
                stopped++;
            }
        }
        // Increment run ID after stopping
        if (stopped > 0) {
            runId++;
            _updateRunIdDisplay();
        }
        App.toast('Stopping all stacks...', 'info');
    }

    function resolveHostPath(containerPath) {
        if (!stacksHostPath || !containerPath) return '';
        if (containerPath.startsWith(stacksContainerPath)) {
            return stacksHostPath + containerPath.slice(stacksContainerPath.length);
        }
        return containerPath;
    }

    function getStacksHostPath() { return stacksHostPath; }

    function refreshStatus() {
        WS.sendOrch({ cmd: 'get_stack_status' });
    }

    function getTestName() { return testName; }
    function setTestName(name) {
        testName = name;
        _updateTestNameDisplay();
    }
    function getRunId() { return runId; }
    function setRunId(id) {
        runId = id;
        _updateRunIdDisplay();
    }

    function _updateTestNameDisplay() {
        const el = document.getElementById('test-name-value');
        if (el && !el.querySelector('input')) el.textContent = testName || 'test_default';
    }

    function _updateRunIdDisplay() {
        const el = document.getElementById('run-id-value');
        if (el) el.textContent = runId;
    }

    return {
        init, launchStack, stopStack, launchAllStacks, stopAllStacks,
        refreshStatus, resolveHostPath, getStacksHostPath,
        getTestName, setTestName, getRunId, setRunId,
    };
})();
