"""Apply semantic exclusion to the pinned Mindcraft collection skill."""
from pathlib import Path
import sys

root = Path(sys.argv[1])
path = root / 'src/agent/library/skills.js'
source = path.read_text()
start = source.index('export async function collectBlock(')
end = source.index('export async function pickupNearbyItems(', start)
section = source[start:end]
changes = {
    '    let blocktypes = [blockType];': '    return withSemanticCollection(bot, async refreshSemanticRegions => {\n    let blocktypes = [blockType];',
    '        let blocks = world.getNearestBlocksWhere(bot, block => {':
        '        const isProtected = await refreshSemanticRegions();\n'
        '        let blocks = world.getNearestBlocksWhere(bot, block => {\n'
        '            if (isProtected(block)) return false;',
    '    return collected > 0;': '    return collected > 0;\n    });',
    'No ${blockType} nearby to collect.': 'No unprotected ${blockType} nearby to collect.',
    'No more ${blockType} nearby to collect.': 'No more unprotected ${blockType} nearby to collect.',
}
for old, new in changes.items():
    if section.count(old) != 1:
        raise RuntimeError('Pinned collection source mismatch: ' + old)
    section = section.replace(old, new, 1)
path.write_text("import { withSemanticCollection } from './semantic_collection.mjs';\n" + source[:start] + section + source[end:])
