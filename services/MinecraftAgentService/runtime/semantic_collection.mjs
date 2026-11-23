import { readdir, readFile, stat } from 'node:fs/promises';
import { join } from 'node:path';

const caches = new Map();
const dimension = value => ({ overworld: 'minecraft:overworld', the_nether: 'minecraft:the_nether', the_end: 'minecraft:the_end' }[value] || value);

export function buildIndex(regions) {
    const chunks = new Map(), large = [];
    for (const region of regions) {
        const g = region.geometry;
        if (region.schema_version !== 1 || !region.dimension || !g || !['cuboid', 'polygon'].includes(g.shape)
            || !['x', 'y', 'z'].every(axis => Number.isSafeInteger(g.min?.[axis]) && Number.isSafeInteger(g.max?.[axis]) && g.min[axis] <= g.max[axis])
            || (g.shape === 'polygon' && (!Array.isArray(g.points) || g.points.length < 3 || !g.points.every(p => Number.isSafeInteger(p.x) && Number.isSafeInteger(p.z)))))
            throw new Error('Invalid semantic region: ' + region.id);
        const x0 = Math.floor(g.min.x / 16), x1 = Math.floor(g.max.x / 16);
        const z0 = Math.floor(g.min.z / 16), z1 = Math.floor(g.max.z / 16);
        if ((x1 - x0 + 1) * (z1 - z0 + 1) > 4096) { large.push(region); continue; }
        for (let x = x0; x <= x1; x++) for (let z = z0; z <= z1; z++) {
            const key = `${region.dimension}:${x}:${z}`;
            if (!chunks.has(key)) chunks.set(key, []);
            chunks.get(key).push(region);
        }
    }
    return (position, dim) => {
        if (!dim) throw new Error('Cannot determine dimension for semantic collection protection.');
        const key = `${dimension(dim)}:${Math.floor(position.x / 16)}:${Math.floor(position.z / 16)}`;
        return [...(chunks.get(key) || []), ...large].some(r => r.dimension === dimension(dim) && contains(r.geometry, position));
    };
}

function contains(g, p) {
    if (['x', 'y', 'z'].some(a => p[a] < g.min[a] || p[a] > g.max[a])) return false;
    if (g.shape === 'cuboid') return true;
    let inside = false;
    for (let i = 0, j = g.points.length - 1; i < g.points.length; j = i++) {
        const a = g.points[j], b = g.points[i];
        if ((p.x - a.x) * (b.z - a.z) === (p.z - a.z) * (b.x - a.x)
            && p.x >= Math.min(a.x, b.x) && p.x <= Math.max(a.x, b.x)
            && p.z >= Math.min(a.z, b.z) && p.z <= Math.max(a.z, b.z)) return true;
        if ((a.z > p.z) !== (b.z > p.z) && p.x < (b.x - a.x) * (p.z - a.z) / (b.z - a.z) + a.x) inside = !inside;
    }
    return inside;
}

export async function loadIndex(directory) {
    // 每次采集目标/挖掘前检查文件元数据；未变动时复用解析结果和空间索引。
    const names = (await readdir(directory)).filter(n => n.endsWith('.json')).sort();
    const metadata = await Promise.all(names.map(async name => {
        const info = await stat(join(directory, name), { bigint: true });
        if (!info.isFile() || info.size > 1048576) throw new Error('Invalid semantic map file: ' + name);
        return `${name}:${info.ino}:${info.size}:${info.mtimeNs}:${info.ctimeNs}`;
    }));
    const signature = JSON.stringify(metadata);
    const old = caches.get(directory);
    if (old?.signature === signature) return old.index;
    const regions = await Promise.all(names.map(async name => JSON.parse(await readFile(join(directory, name), 'utf8'))));
    const index = buildIndex(regions);
    caches.set(directory, { signature, index });
    return index;
}

export async function withSemanticCollection(bot, action, directory = process.env.SEMANTIC_REGIONS_DIR) {
    if (!directory) return action(async () => () => false);
    if (bot.__semanticCollectionActive) throw new Error('A semantic collection action is already running.');
    bot.__semanticCollectionActive = true;
    const originalDig = bot.dig, originalSet = bot.pathfinder.setMovements;
    const originalMovements = bot.pathfinder.movements;
    const restores = new Map();
    let index;
    const protectedBlock = block => index(block.position, bot.game.dimension);
    const protectMovements = movements => {
        if (!movements || restores.has(movements)) return;
        const original = movements.safeToBreak;
        movements.safeToBreak = function (block) { return !protectedBlock(block) && original.call(this, block); };
        restores.set(movements, original);
    };
    const refresh = async () => { index = await loadIndex(directory); return protectedBlock; };
    try {
        await refresh();
        protectMovements(originalMovements);
        bot.pathfinder.setMovements = function (movements) {
            protectMovements(movements);
            return originalSet.call(this, movements);
        };
        bot.dig = async function (block, ...args) {
            await refresh();
            if (protectedBlock(block)) throw new Error('Collection blocked: block is inside a semantic region.');
            return originalDig.call(this, block, ...args);
        };
        return await action(refresh);
    } finally {
        bot.dig = originalDig;
        bot.pathfinder.setMovements = originalSet;
        for (const [movements, safeToBreak] of restores) movements.safeToBreak = safeToBreak;
        if (originalMovements) originalSet.call(bot.pathfinder, originalMovements);
        delete bot.__semanticCollectionActive;
    }
}
