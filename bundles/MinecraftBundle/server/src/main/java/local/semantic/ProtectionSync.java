package local.semantic;

import com.sk89q.worldedit.bukkit.BukkitAdapter;
import com.sk89q.worldedit.math.BlockVector2;
import com.sk89q.worldedit.math.BlockVector3;
import com.sk89q.worldguard.WorldGuard;
import com.sk89q.worldguard.protection.flags.Flags;
import com.sk89q.worldguard.protection.flags.StateFlag;
import com.sk89q.worldguard.protection.managers.RegionManager;
import com.sk89q.worldguard.protection.managers.RemovalStrategy;
import com.sk89q.worldguard.protection.regions.ProtectedRegion;
import com.sk89q.worldguard.protection.regions.ProtectedCuboidRegion;
import com.sk89q.worldguard.protection.regions.ProtectedPolygonalRegion;
import org.bukkit.World;
import org.bukkit.plugin.java.JavaPlugin;
import java.util.*;

/** The semantic_ WorldGuard namespace is exclusively managed from region JSON. */
final class ProtectionSync {
    static final String PREFIX = "semantic_";
    private final JavaPlugin plugin;
    private final RegionStore store;
    private Map<String, RegionData> previous;
    private String lastError;

    ProtectionSync(JavaPlugin plugin, RegionStore store) {
        this.plugin = plugin;
        this.store = store;
    }

    static ProtectedRegion region(RegionData data) {
        var g = data.geometry();
        if (g == null || g.min() == null || g.max() == null
                || g.min().x() > g.max().x() || g.min().y() > g.max().y() || g.min().z() > g.max().z())
            throw new IllegalArgumentException("Invalid bounds: " + data.id());
        String id = PREFIX + data.id();
        ProtectedRegion region;
        if ("cuboid".equals(g.shape())) {
            region = new ProtectedCuboidRegion(id,
                    BlockVector3.at(g.min().x(), g.min().y(), g.min().z()),
                    BlockVector3.at(g.max().x(), g.max().y(), g.max().z()));
        } else if ("polygon".equals(g.shape())) {
            if (g.points() == null || g.points().size() < 3)
                throw new IllegalArgumentException("Polygon requires at least three vertices: " + data.id());
            region = new ProtectedPolygonalRegion(id,
                    g.points().stream().map(p -> BlockVector2.at(p.x(), p.z())).toList(),
                    g.min().y(), g.max().y());
        } else throw new IllegalArgumentException("Unsupported shape: " + data.id());
        // 关闭默认领地成员限制，只显式禁止拆放；门、床、容器等保持原版行为。
        region.setFlag(Flags.PASSTHROUGH, StateFlag.State.ALLOW);
        region.setFlag(Flags.BLOCK_BREAK, StateFlag.State.DENY);
        region.setFlag(Flags.BLOCK_PLACE, StateFlag.State.DENY);
        return region;
    }

    String sync(boolean force) {
        try {
            Map<String, RegionData> current = new TreeMap<>();
            for (String id : store.list()) current.put(id, store.read(id));
            if (!force && current.equals(previous)) return "Protection unchanged: " + current.size() + " regions.";
            // 先验证所有文件和目标世界，任何错误都保留上次有效保护，不误解除保护。
            Map<World, Map<String, ProtectedRegion>> plan = new LinkedHashMap<>();
            Map<World, RegionManager> managers = new LinkedHashMap<>();
            for (World world : plugin.getServer().getWorlds()) {
                var manager = WorldGuard.getInstance().getPlatform().getRegionContainer().get(BukkitAdapter.adapt(world));
                if (manager == null) throw new IllegalStateException("WorldGuard unavailable: " + world.getName());
                managers.put(world, manager);
                plan.put(world, new LinkedHashMap<>());
            }
            for (RegionData data : current.values()) {
                World world = plugin.getServer().getWorld(data.world());
                if (world == null) throw new IllegalArgumentException("World not loaded: " + data.world());
                String dimension = switch (world.getEnvironment()) {
                    case NORMAL -> "minecraft:overworld";
                    case NETHER -> "minecraft:the_nether";
                    case THE_END -> "minecraft:the_end";
                    default -> world.getKey().toString();
                };
                if (!dimension.equals(data.dimension())) throw new IllegalArgumentException("Dimension mismatch: " + data.id());
                // 导入同一存档时 Paper 可能重新生成 UUID，世界名与维度决定保护落点。
                if (!world.getUID().toString().equals(data.worldUuid()))
                    plugin.getLogger().warning("Region " + data.id() + " has an older world UUID; using world name " + world.getName());
                ProtectedRegion region = region(data);
                plan.get(world).put(region.getId(), region);
            }
            for (var entry : plan.entrySet()) {
                RegionManager manager = managers.get(entry.getKey());
                var desired = entry.getValue();
                for (String id : new ArrayList<>(manager.getRegions().keySet())) {
                    if (id.startsWith(PREFIX) && !desired.containsKey(id))
                        manager.removeRegion(id, RemovalStrategy.UNSET_PARENT_IN_CHILDREN);
                }
                for (ProtectedRegion region : desired.values()) manager.addRegion(region);
                manager.saveChanges();
            }
            previous = current;
            lastError = null;
            String result = "Protection synced: " + current.size() + " regions (block-break/place denied only).";
            plugin.getLogger().info(result);
            return result;
        } catch (Exception error) {
            String message = "Protection sync failed: " + error.getMessage();
            if (!message.equals(lastError)) plugin.getLogger().severe(message);
            lastError = message;
            return message;
        }
    }
}
