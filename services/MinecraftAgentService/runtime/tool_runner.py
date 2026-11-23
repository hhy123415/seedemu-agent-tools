"""Execute service-owned handlers through the existing authorized ToolRegistry."""
import contextlib
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
from emuvista_agent.runtime import ToolRegistry


def registry(path):
    config = json.loads(Path(path).read_text())
    context = SimpleNamespace(config=config, accounts=config['accounts'],
                              tool_config=config['tool_config'], emit=lambda *a, **k: None)
    context.tools = ToolRegistry(context)
    return context.tools


def main():
    try:
        tools = registry(os.environ.get('MINDCRAFT_TOOL_CONFIG', '/mindcraft/tools.json'))
        if sys.argv[1:] == ['--list']:
            result = tools.list()
        else:
            call = json.load(sys.stdin)
            # Keep handler diagnostics out of the machine-readable response.
            with contextlib.redirect_stdout(sys.stderr):
                result = tools.invoke(call['name'], call['arguments'])
        print(json.dumps(result, allow_nan=False))
    except Exception as error:
        print(json.dumps({'error': str(error)}))
        sys.exit(1)


if __name__ == '__main__':
    main()
