/**
 * Orchestrator module — manages agent stack lifecycle from the UI.
 */

const Orchestrator = (() => {
    function init() {
        WS.on('orch:stack_update', (data) => {
            Agents.updateStackStatus(data.agent_id, data.status);
            if (data.status === 'RUNNING') {
                App.toast(`Stack for ${data.agent_id} is running`, 'success');
            } else if (data.status === 'ERROR') {
                App.toast(`Stack error for ${data.agent_id}: ${data.error || 'unknown'}`, 'error');
            } else if (data.status === 'STOPPED') {
                App.toast(`Stack for ${data.agent_id} stopped`);
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

        const composeFile = agent.stack_compose_file || './stacks/agent_stack.yml';
        if (!composeFile) {
            App.toast(`No compose file set for ${agentId}`, 'error');
            return;
        }

        // Merge default env with stored env (stored values take precedence)
        const env = {
            AGENT_ID: agentId,
            ROS_DOMAIN_ID: String(agent.domain_id),
            AGENT_NAMESPACE: agentId,
            ...(agent.stack_env || {}),
        };

        WS.sendOrch({
            cmd: 'launch_stack',
            agent_id: agentId,
            compose_file: composeFile,
            env,
        });

        Agents.updateStackStatus(agentId, 'STARTING');
        App.toast(`Launching stack for ${agentId}...`, 'info');
    }

    function stopStack(agentId) {
        WS.sendOrch({
            cmd: 'stop_stack',
            agent_id: agentId,
        });

        Agents.updateStackStatus(agentId, 'STOPPING');
        App.toast(`Stopping stack for ${agentId}...`, 'info');
    }

    function refreshStatus() {
        WS.sendOrch({ cmd: 'get_stack_status' });
    }

    return { init, launchStack, stopStack, refreshStatus };
})();
