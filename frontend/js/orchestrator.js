/**
 * Orchestrator module — manages agent stack lifecycle from the UI.
 */

const Orchestrator = (() => {
    function init() {
        WS.on('orch:stack_update', (data) => {
            Agents.updateStackStatus(data.agent_name, data.status);
            if (data.status === 'RUNNING') {
                App.toast(`Stack for ${data.agent_name} is running`, 'success');
            } else if (data.status === 'ERROR') {
                App.toast(`Stack error for ${data.agent_name}: ${data.error || 'unknown'}`, 'error');
            } else if (data.status === 'STOPPED') {
                App.toast(`Stack for ${data.agent_name} stopped`);
            }
        });

        WS.on('orch:stack_status', (data) => {
            for (const [agentId, info] of Object.entries(data.stacks || {})) {
                Agents.updateStackStatus(agentId, info.status);
            }
        });
    }

    function launchStack(agentId) {
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
        App.toast(`Launching stack for ${agentId}...`, 'info');
    }

    function stopStack(agentId) {
        WS.sendOrch({
            cmd: 'stop_stack',
            agent_name: agentId,
        });

        Agents.updateStackStatus(agentId, 'STOPPING');
        App.toast(`Stopping stack for ${agentId}...`, 'info');
    }

    function refreshStatus() {
        WS.sendOrch({ cmd: 'get_stack_status' });
    }

    return { init, launchStack, stopStack, refreshStatus };
})();
