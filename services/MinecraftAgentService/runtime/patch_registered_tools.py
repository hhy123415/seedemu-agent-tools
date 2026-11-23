"""Adapt native Mindcraft commands to registered service tool schemas."""
from pathlib import Path
import sys

path = Path(sys.argv[1]) / 'src/agent/commands/index.js'
source = path.read_text()
changes = {
    'const commandMap = {};': "for (const tool of registeredTools) {\n"
        "    if (commandList.some(command => command.name === tool.name)) throw new Error('Duplicate tool command: ' + tool.name);\n"
        "}\nactionsList.push(...registeredTools);\ncommandList.push(...registeredTools);\nconst commandMap = {};",
    'export function parseCommandMessage(message) {': 'export function parseCommandMessage(message) {\n'
        '    const tool = parseRegisteredTool(message);\n    if (tool) return tool.error || tool;',
    'export function truncCommandMessage(message) {': 'export function truncCommandMessage(message) {\n'
        '    const tool = parseRegisteredTool(message);\n    if (tool) return tool.text || message;',
}
for old, new in changes.items():
    if source.count(old) != 1:
        raise RuntimeError('Pinned Mindcraft tool registration mismatch: ' + old)
    source = source.replace(old, new, 1)
path.write_text("import { registeredTools, parseRegisteredTool } from './registered_tools.mjs';\n" + source)
