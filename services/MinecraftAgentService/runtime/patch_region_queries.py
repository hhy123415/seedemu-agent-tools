"""Register local read-only map queries in the pinned native Mindcraft command list."""
from pathlib import Path
import sys

path = Path(sys.argv[1]) / 'src/agent/commands/index.js'
source = path.read_text()
old = 'const commandList = queryList.concat(actionsList);'
if source.count(old) != 1:
    raise RuntimeError('Pinned Mindcraft command registration mismatch')
source = "import { regionQueryList } from './region_queries.mjs';\n" + source.replace(
    old, 'const commandList = queryList.concat(regionQueryList, actionsList);', 1)
path.write_text(source)
