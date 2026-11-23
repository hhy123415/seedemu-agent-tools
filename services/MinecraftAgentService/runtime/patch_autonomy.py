"""Wire startup and control commands into the pinned upstream native goal loop."""
from pathlib import Path
import sys

root = Path(sys.argv[1])
changes = {
    'src/agent/agent.js': [
        ('            if (username === this.name) return;',
         '            if (username === this.name || (settings.ignored_players || []).includes(username)) return;'),
        ("        if (save_data?.self_prompt) {", "        if (await initializeAutonomy(this, save_data)) return;\n\n        if (save_data?.self_prompt) {"),
    ],
    'src/agent/commands/index.js': [
        ('const commandList = queryList.concat(regionQueryList, actionsList);',
         "actionsList.push(...autonomyCommands.filter(command => command.name !== '!taskStatus'));\n"
         "const commandList = queryList.concat(regionQueryList, autonomyCommands.filter(command => command.name === '!taskStatus'), actionsList);"),
    ],
    'src/agent/commands/actions.js': [
        ("            agent.self_prompter.stop();\n            return 'Self-prompting stopped.';",
         "            if (agent.autonomy) return await agent.autonomy.complete();\n            await agent.self_prompter.stop();\n            return 'Self-prompting stopped.';"),
    ],
}
imports = {
    'src/agent/agent.js': "import { initializeAutonomy } from './autonomy.mjs';\n",
    'src/agent/commands/index.js': "import { autonomyCommands } from '../autonomy.mjs';\n",
}
pending = {}
for name, replacements in changes.items():
    path = root / name
    text = path.read_text()
    for before, after in replacements:
        if text.count(before) != 1:
            raise RuntimeError(f'Pinned source mismatch: {name}')
        text = text.replace(before, after, 1)
    pending[path] = imports.get(name, '') + text
for path, text in pending.items():
    path.write_text(text)
