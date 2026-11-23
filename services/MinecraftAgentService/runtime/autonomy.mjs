import { readFileSync, writeFileSync, renameSync, existsSync, mkdirSync, appendFileSync } from 'node:fs';
import { dirname } from 'node:path';

export function readConfig(path = process.env.PERSONA_CONFIG || '/mindcraft/persona.json') {
    const config = JSON.parse(readFileSync(path, 'utf8'));
    if (typeof config.persona !== 'string' || !config.persona.trim()
        || typeof config.auto_start !== 'boolean' || typeof config.resume_on_restart !== 'boolean'
        || !Number.isInteger(config.cooldown_ms) || config.cooldown_ms < 2000
        || !Number.isInteger(config.decision_interval_ms) || config.decision_interval_ms < 30000)
        throw new Error('Invalid persona configuration: persona, auto_start, resume_on_restart, cooldown_ms >= 2000 and decision_interval_ms >= 30000 required.');
    return config;
}

export async function initializeAutonomy(agent, saved, options = {}) {
    const configPath = options.configPath || process.env.PERSONA_CONFIG || '/mindcraft/persona.json';
    const statePath = options.statePath || `./bots/${agent.name}/autonomy-state.json`;
    const now = options.now || Date.now;
    let config, state;
    try {
        config = readConfig(configPath);
        state = existsSync(statePath) ? JSON.parse(readFileSync(statePath, 'utf8')) : null;
        // 旧预设目标不会迁入人设模式；明确暂停或停止的意图仍然保留。
        if (state?.version !== 2) state = { version: 2, status:
            ['paused', 'stopped', 'failed'].includes(state?.status) ? state.status : 'idle',
            phase: 'selecting', goal: '', source: 'persona', recent: [] };
        if (!['idle', 'running', 'waiting', 'paused', 'stopped', 'failed'].includes(state.status)
            || !['selecting', 'executing'].includes(state.phase) || typeof state.goal !== 'string'
            || !Array.isArray(state.recent)) throw new Error('Invalid autonomy state');
    } catch (error) {
        console.error('[Autonomy] Configuration/state rejected; not starting:', error.message);
        return true;
    }
    const persist = () => {
        mkdirSync(dirname(statePath), { recursive: true });
        state.updated_at = new Date(now()).toISOString();
        writeFileSync(`${statePath}.tmp`, JSON.stringify(state, null, 2) + '\n');
        renameSync(`${statePath}.tmp`, statePath);
    };
    const record = (event, detail = {}) => {
        persist();
        appendFileSync(`${statePath}.events.jsonl`, JSON.stringify({ at: state.updated_at, event, ...detail }) + '\n');
    };
    const sp = agent.self_prompter;
    const start = sp.start.bind(sp), stop = sp.stop.bind(sp), pause = sp.pause.bind(sp);
    const loop = sp.startLoop.bind(sp), update = sp.update.bind(sp);
    const setPaused = sp.setPromptPaused.bind(sp);
    // 人设是长期动机；目标须由模型结合工具观察生成，不由程序指定游戏行为。
    const selectionPrompt = () => `Your persona: ${config.persona}\nObserve your current time, location, health, inventory and relevant surroundings using tools. Decide one small goal consistent with your persona and current needs. Before executing it call !chooseGoal("goal", "reason including observations and a success criterion"). Do not assume an observation or invent a need. If no action is warranted call !waitForSituation("reason"). Avoid repeating recently completed or blocked goals unless observations justify it. Recent outcomes: ${JSON.stringify(state.recent)}.`;
    const launch = () => {
        state.status = 'running';
        delete state.error;
        sp.cooldown = config.cooldown_ms;
        persist();
        start(state.phase === 'selecting' ? selectionPrompt() : state.goal);
    };
    sp.start = goal => {
        if (!goal?.trim()) return 'Specify a goal.';
        state.phase = 'executing'; state.goal = goal; state.source = 'manual';
        record('manual_goal', { goal });
        launch();
    };
    sp.stop = async (...args) => {
        state.status = 'stopped'; record('stopped');
        return stop(...args);
    };
    sp.pause = async () => {
        state.status = 'paused'; record('paused', { goal: state.goal });
        return pause();
    };
    sp.setPromptPaused = goal => {
        state.status = 'paused'; state.phase = 'executing'; state.goal = goal; state.source = 'manual';
        record('manual_goal_paused', { goal });
        return setPaused(goal);
    };
    sp.startLoop = async () => {
        try { await loop(); }
        catch (error) {
            state.status = 'failed'; state.error = String(error.message || error);
            sp.state = 0; sp.loop_active = false; sp.interrupt = false;
            record('failed', { error: state.error });
        } finally {
            if (sp.isStopped() && state.status === 'running') {
                state.status = 'stopped'; record('loop_stopped');
            }
            persist();
        }
    };
    // 复用原生更新节拍，等待当前循环彻底退出；不启动并行决策循环。
    sp.update = delta => {
        if (state.status === 'waiting' && now() >= state.next_decision_at
            && !sp.loop_active && !sp.interrupt && agent.isIdle()) {
            state.phase = 'selecting'; state.source = 'persona'; state.goal = '';
            launch();
        }
        update(delta);
    };
    const wait = async (reason, completed = false) => {
        if (state.status !== 'running') return 'Autonomy is not running.';
        if (completed && state.phase !== 'executing') return 'Choose and execute a goal before completing it.';
        const outcome = { goal: state.goal, reason, outcome: completed ? 'agent_reported_complete' : 'waiting' };
        // 手动目标完成后停止；人设目标完成后延迟重新观察。
        state.status = state.source === 'manual' ? 'stopped' : 'waiting';
        state.next_decision_at = now() + config.decision_interval_ms;
        state.recent = [...state.recent, outcome].slice(-10);
        record(completed ? 'goal_completed' : 'waiting', outcome);
        await stop();
        return completed ? 'Completion recorded. Rest before deciding again.' : 'Waiting before observing again.';
    };
    agent.autonomy = {
        status: () => ({ ...state, loop_active: sp.loop_active }),
        startConfigured: () => {
            if (sp.loop_active || (!sp.isStopped() && state.status !== 'paused')) return 'Stop current work first.';
            config = readConfig(configPath);
            state.phase = 'selecting'; state.goal = ''; state.source = 'persona';
            launch(); return 'Persona autonomy started; observe and choose a goal.';
        },
        choose: (goal, reason) => {
            if (state.status !== 'running' || state.phase !== 'selecting') return 'Not selecting a goal.';
            if (!goal?.trim() || !reason?.trim() || goal.length > 4000 || reason.length > 4000) return 'Provide a concise goal and reason.';
            state.goal = goal; state.reason = reason; state.phase = 'executing'; state.source = 'persona';
            sp.prompt = goal;
            record('goal_selected', { goal, reason });
            return 'Goal recorded. Execute it and verify the result before !endGoal.';
        },
        wait: reason => wait(reason),
        complete: () => wait('Model reported success; inspect tool history for evidence.', true),
        resume: () => {
            if (!['paused', 'stopped', 'failed'].includes(state.status) || sp.loop_active) return 'Cannot resume in this state.';
            launch(); return 'Autonomy resumed.';
        },
    };
    if ((state.status === 'idle' && config.auto_start)
        || (['running', 'waiting'].includes(state.status) && config.resume_on_restart)) {
        if (state.status !== 'waiting') launch();
    } else {
        if (['running', 'waiting'].includes(state.status)) state.status = 'paused';
        sp.prompt = state.phase === 'selecting' ? selectionPrompt() : state.goal;
        persist();
    }
    record('ready', { status: state.status });
    return true;
}

const controller = agent => {
    if (!agent.autonomy) throw new Error('Autonomy unavailable; check persona configuration and logs.');
    return agent.autonomy;
};
const safely = fn => async (agent, ...args) => {
    try { return await fn(agent, ...args); } catch (error) { return `Autonomy error: ${error.message}`; }
};
export const autonomyCommands = [
    { name: '!taskStatus', description: 'Inspect autonomy state and recent agent-reported outcomes.', perform: safely(a => JSON.stringify(controller(a).status())) },
    { name: '!chooseGoal', description: 'After observing, record a self-chosen goal, reasons and success criterion before executing it.',
        params: { goal: { type: 'string', description: 'One concrete goal.' }, reason: { type: 'string', description: 'Observed need, persona motivation, and success criterion.' } },
        perform: safely((a, goal, reason) => controller(a).choose(goal, reason)) },
    { name: '!waitForSituation', description: 'Wait before reconsidering when there is no justified action.',
        params: { reason: { type: 'string', description: 'Why waiting is appropriate.' } },
        perform: safely((a, reason) => controller(a).wait(reason)) },
    { name: '!startTask', description: 'Explicitly start persona-driven observation and goal selection.', perform: safely(a => controller(a).startConfigured()) },
    { name: '!pauseTask', description: 'Pause autonomy until explicitly resumed, including across restarts.', perform: safely(async a => { controller(a); await a.self_prompter.pause(); return 'Paused.'; }) },
    { name: '!resumeTask', description: 'Explicitly resume paused or stopped autonomy.', perform: safely(a => controller(a).resume()) },
    { name: '!stopTask', description: 'Stop autonomy until explicitly resumed, including across restarts.', perform: safely(async a => { controller(a); await a.self_prompter.stop(); return 'Stopped.'; }) },
];
