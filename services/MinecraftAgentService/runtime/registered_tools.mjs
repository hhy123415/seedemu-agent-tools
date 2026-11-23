import { execFileSync, spawn } from 'node:child_process';

const runner = process.env.MINDCRAFT_TOOL_RUNNER || '/mindcraft/tool_runner.py';
const definitions = JSON.parse(execFileSync('python3', [runner, '--list'], { encoding: 'utf8' }));
const names = new Map();
export const registeredTools = definitions.map(definition => {
    const name = '!' + definition.name.replaceAll('.', '_');
    if (names.has(name)) throw new Error('Duplicate registered tool command: ' + name);
    names.set(name, definition.name);
    return {
        name,
        // JSON 对象保留原有 schema 的类型、可选参数和嵌套结构，交给原注册表校验。
        description: definition.description + ' Call as ' + name + '(<JSON object>). Schema: '
            + JSON.stringify(definition.input_schema),
        params: { arguments: { type: 'object', description: 'Arguments matching the JSON schema above.' } },
        perform: async (_agent, argumentsObject) => new Promise(resolve => {
            const child = spawn('python3', [runner], { stdio: ['pipe', 'pipe', 'pipe'] });
            let output = '';
            let finished = false;
            const finish = value => {
                if (finished) return;
                finished = true;
                clearTimeout(timer);
                resolve(value);
            };
            // 中止后结果可能未知；不自动重试会产生副作用的工具。
            const timer = setTimeout(() => {
                child.kill('SIGKILL');
                finish(JSON.stringify({ error: 'Tool timed out; outcome may be unknown. Verify state before retrying.' }));
            }, 60000);
            child.stdout.on('data', chunk => {
                output += chunk;
                if (output.length > 1048576) {
                    child.kill('SIGKILL');
                    finish(JSON.stringify({ error: 'Tool response exceeded size limit; verify state before retrying.' }));
                }
            });
            child.stderr.resume();
            child.on('error', error => finish(JSON.stringify({ error: error.message })));
            child.stdin.on('error', () => {});
            child.on('close', () => finish(output.trim() || JSON.stringify({ error: 'Tool exited without a result; verify state before retrying.' })));
            child.stdin.end(JSON.stringify({ name: definition.name, arguments: argumentsObject }));
        })
    };
});

// 原生解析器不支持 JSON 对象；仅扩展已注册工具，保留其他命令的原有语法。
export function parseRegisteredTool(message) {
    const match = /!(\w+)/.exec(message);
    if (!match || !names.has('!' + match[1])) return null;
    const commandName = '!' + match[1];
    const start = match.index + match[0].length;
    const rest = message.slice(start).trimStart();
    if (!rest.startsWith('(')) return { error: 'Use ' + commandName + '(<JSON object>), including {} for no arguments.' };
    let quoted = false, escaped = false, depth = 0;
    for (let i = 1; i < rest.length; i++) {
        const char = rest[i];
        if (quoted) {
            if (escaped) escaped = false;
            else if (char === '\\') escaped = true;
            else if (char === '"') quoted = false;
        } else if (char === '"') quoted = true;
        else if (char === '{' || char === '[') depth++;
        else if (char === '}' || char === ']') depth--;
        else if (char === ')' && depth === 0) {
            try {
                const args = JSON.parse(rest.slice(1, i));
                if (!args || typeof args !== 'object' || Array.isArray(args)) throw new Error();
                return { commandName, args: [args], text: message.slice(0, start) + rest.slice(0, i + 1) };
            } catch { return { error: 'Tool arguments must be a valid JSON object.' }; }
        }
    }
    return { error: 'Incomplete tool call; use ' + commandName + '(<JSON object>).' };
}
