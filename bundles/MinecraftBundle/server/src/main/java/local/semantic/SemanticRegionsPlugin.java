package local.semantic;

import com.sk89q.worldedit.IncompleteRegionException;
import com.sk89q.worldedit.WorldEdit;
import com.sk89q.worldedit.bukkit.BukkitAdapter;
import com.sk89q.worldedit.math.BlockVector3;
import com.sk89q.worldedit.regions.CuboidRegion;
import com.sk89q.worldedit.regions.Polygonal2DRegion;
import org.bukkit.command.Command;
import org.bukkit.command.CommandSender;
import org.bukkit.entity.Player;
import org.bukkit.plugin.java.JavaPlugin;
import java.io.IOException;
import java.time.Instant;
import java.util.*;
import java.util.logging.Level;

public final class SemanticRegionsPlugin extends JavaPlugin {
    private RegionStore store;
    private ProtectionSync protection;
    private static final List<String> COMMANDS = List.of("help", "save", "list", "info", "rename",
            "type", "describe", "entrance", "clearentrance", "reselect", "delete", "sync");

    @Override public void onEnable() {
        try {
            store = new RegionStore(getDataFolder().toPath().resolve("regions"));
            protection = new ProtectionSync(this, store);
            getServer().getScheduler().runTaskTimer(this, () -> protection.sync(false), 1L, 40L);
            getLogger().info("Semantic JSON directory: " + getDataFolder().toPath().resolve("regions").toAbsolutePath());
        } catch (IOException e) {
            getLogger().log(Level.SEVERE, "Cannot open semantic region storage", e);
            getServer().getPluginManager().disablePlugin(this);
        }
    }

    @Override public boolean onCommand(CommandSender sender, Command command, String label, String[] args) {
        if (!sender.hasPermission("semantic.admin")) {
            sender.sendMessage("你没有管理语义区域的权限。");
            return true;
        }
        try {
            execute(sender, args);
            protection.sync(false);
        } catch (IllegalArgumentException e) {
            sender.sendMessage("[区域] " + e.getMessage());
        } catch (IncompleteRegionException e) {
            sender.sendMessage("[区域] 请先用 WorldEdit 完成选区：//wand 或 //pos1、//pos2。");
        } catch (IOException e) {
            sender.sendMessage("[区域] 文件操作失败，未确认保存成功，请查看服务器日志。");
            getLogger().log(Level.SEVERE, "Semantic region storage failed", e);
        }
        return true;
    }

    private void execute(CommandSender sender, String[] args) throws IOException, IncompleteRegionException {
        String action = args.length == 0 ? "help" : args[0].toLowerCase(Locale.ROOT);
        if (action.equals("sync")) {
            sender.sendMessage("[区域] " + protection.sync(true));
            return;
        }
        if (action.equals("help")) {
            sender.sendMessage(new String[]{
                "[区域] 先用 WorldEdit 选区，支持长方体和带高度的多边形。",
                "/semantic save <id> <type> <名称，可含空格> — 创建并导出 JSON",
                "/semantic list | info <id>",
                "/semantic sync — 立即从地图 JSON 同步建筑保护（平时每 2 秒自动同步）",
                "/semantic rename <id> <名称> | type <id> <类型> | describe <id> <描述>",
                "/semantic entrance <id> — 将脚下方块坐标及朝向标记为入口",
                "/semantic clearentrance <id> | reselect <id> — 清除入口 / 更新选区",
                "/semantic delete <id> — 删除区域 JSON；不会修改世界方块"});
            return;
        }
        if (action.equals("list")) {
            sender.sendMessage("[区域] " + String.join(", ", store.list()));
            return;
        }
        if (!COMMANDS.contains(action)) throw new IllegalArgumentException("未知命令，请用 /semantic help。");
        require(args, 2, "/semantic " + action + " <id>");
        String id = args[1];
        String now = Instant.now().toString();
        if (action.equals("save")) {
            require(args, 4, "/semantic save <id> <type> <名称>");
            if (store.exists(id)) throw new IllegalArgumentException("区域已存在；用 reselect、rename、type 或 describe 修改。");
            Player player = player(sender);
            var world = player.getWorld();
            String dimension = switch (world.getEnvironment()) {
                case NORMAL -> "minecraft:overworld";
                case NETHER -> "minecraft:the_nether";
                case THE_END -> "minecraft:the_end";
                default -> world.getKey().toString();
            };
            store.write(new RegionData(1, id, text(args, 3), text(args, 2, 3), "",
                    world.getName(), world.getUID().toString(), dimension, selection(player), null,
                    player.getUniqueId().toString(), now, now));
        } else {
            RegionData data = store.read(id);
            switch (action) {
                case "info" -> {
                    sender.sendMessage("[区域] " + data.id() + " | " + data.name() + " | " + data.type()
                            + " | " + data.world() + " | " + data.geometry().shape()
                            + " " + data.geometry().min() + " → " + data.geometry().max());
                    sender.sendMessage("描述：" + data.description() + "；入口：" + data.entrance());
                    return;
                }
                case "delete" -> {
                    store.delete(id);
                    sender.sendMessage("[区域] 已删除：" + id + "（世界方块未变动）");
                    return;
                }
                case "rename" -> data = data.withMetadata(text(args, 2), data.type(), data.description(), data.entrance(), data.geometry(), now);
                case "type" -> data = data.withMetadata(data.name(), text(args, 2), data.description(), data.entrance(), data.geometry(), now);
                case "describe" -> data = data.withMetadata(data.name(), data.type(), text(args, 2), data.entrance(), data.geometry(), now);
                case "clearentrance" -> data = data.withMetadata(data.name(), data.type(), data.description(), null, data.geometry(), now);
                case "entrance" -> {
                    Player player = sameWorld(sender, data);
                    var location = player.getLocation();
                    // 入口可位于边界外侧，故不强制要求位于选区内。
                    var entrance = new RegionData.Entrance(new RegionData.Point(location.getBlockX(),
                            location.getBlockY(), location.getBlockZ()), location.getYaw());
                    data = data.withMetadata(data.name(), data.type(), data.description(), entrance, data.geometry(), now);
                }
                case "reselect" -> data = data.withMetadata(data.name(), data.type(), data.description(), data.entrance(), selection(sameWorld(sender, data)), now);
                default -> throw new IllegalArgumentException("未知命令。");
            }
            store.write(data);
        }
        sender.sendMessage("[区域] 已保存并导出：" + id + ".json");
    }

    private RegionData.Geometry selection(Player player) throws IncompleteRegionException {
        var session = WorldEdit.getInstance().getSessionManager().get(BukkitAdapter.adapt(player));
        var world = session.getSelectionWorld();
        if (world == null) throw new IncompleteRegionException();
        if (!world.equals(BukkitAdapter.adapt(player.getWorld())))
            throw new IllegalArgumentException("选区与玩家不在同一世界，请重新选区。");
        var region = session.getSelection(world);
        if (region instanceof CuboidRegion)
            return new RegionData.Geometry("cuboid", point(region.getMinimumPoint()), point(region.getMaximumPoint()), List.of());
        if (region instanceof Polygonal2DRegion polygon)
            return new RegionData.Geometry("polygon", point(region.getMinimumPoint()), point(region.getMaximumPoint()),
                    polygon.getPoints().stream().map(p -> new RegionData.Point2(p.x(), p.z())).toList());
        throw new IllegalArgumentException("只支持长方体和多边形；请用 //sel cuboid 或 //sel poly。");
    }

    private static RegionData.Point point(BlockVector3 p) { return new RegionData.Point(p.x(), p.y(), p.z()); }
    private static Player player(CommandSender sender) {
        if (!(sender instanceof Player p)) throw new IllegalArgumentException("此操作须由游戏内玩家执行。");
        return p;
    }
    private static Player sameWorld(CommandSender sender, RegionData data) {
        Player p = player(sender);
        if (!p.getWorld().getUID().toString().equals(data.worldUuid()))
            throw new IllegalArgumentException("请进入该区域所属世界后操作。");
        return p;
    }
    private static void require(String[] args, int count, String usage) {
        if (args.length < count) throw new IllegalArgumentException("用法：" + usage);
    }
    private static String text(String[] args, int start) { return text(args, start, args.length); }
    private static String text(String[] args, int start, int end) {
        require(args, start + 1, "/semantic help（缺少名称、类型或描述）");
        String result = String.join(" ", Arrays.copyOfRange(args, start, end)).trim();
        if (result.isEmpty() || result.length() > 2048) throw new IllegalArgumentException("文本长度须为 1–2048 字符。");
        return result;
    }

    @Override public List<String> onTabComplete(CommandSender sender, Command command, String alias, String[] args) {
        if (!sender.hasPermission("semantic.admin")) return List.of();
        try {
            List<String> choices = args.length == 1 ? COMMANDS
                    : args.length == 2 && !args[0].equalsIgnoreCase("save") ? store.list() : List.of();
            String prefix = args.length == 0 ? "" : args[args.length - 1].toLowerCase(Locale.ROOT);
            return choices.stream().filter(s -> s.startsWith(prefix)).toList();
        } catch (IOException e) { return List.of(); }
    }
}
