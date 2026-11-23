# MinecraftBundle

公共 Minecraft 服务端：Paper 1.21.6 build 48 / Java 21，内置 WorldEdit 7.3.16、WorldGuard 7.0.14 和 SemanticRegions。构建源码统一放在 `server/`，插件由 Maven 构建进镜像。Bundle 不包含 agent、寻路或模型调用。

## 独立 Compose

```python
from bundles.MinecraftBundle import MinecraftBundle

minecraft = (MinecraftBundle()
             .setWorld('world')
             .setRegionPath('map/regions')
             .setDataVolume('minecraft-data')
             .setOperators(['seed'])
             .enableHostAccess(25565))
compose = {
    'services': {'minecraft': minecraft.prepare('output', container_name='minecraft-server')},
    'volumes': minecraft.getVolumes(),
}
```

调用方将 `compose` 写入 `output/docker-compose.yml`。不设置显式镜像名，遵循 Compose 的 `<项目>-<服务>` 命名。E17 是此入口的完整示例。

## SEED 网络

与 PaymentBundle 一样使用 `ContainerBundle` / `PreparedContainer` 生命周期和链式配置。在 emulator render 后关联网络，交给 Docker 编译器：

```python
minecraft = MinecraftBundle(emu).setDataVolume('minecraft-data').enableHostAccess(25565)
minecraft.addInternalNetwork('170', 'net0', ['10.170.0.10'], '10.170.0.254')
minecraft.registerVolumes(compiler)
compiler.addContainerBundle(minecraft)
```

H23 提供完整示例。网络包装层委托原服务端入口运行，仅在配置默认路由时添加 `NET_ADMIN` 能力。独立 Compose 不需要该能力。

## 配置与持久化

- `setWorld(path)`：接受直接含 `level.dat` 的目录，或恰好含一个存档子目录的目录。首次复制到数据卷 `imported_world`，后续启动保留已有进度。省略则正常生成新世界。
- `setRegionPath(path)`：将语义 JSON 目录可写挂载到 SemanticRegions。插件约每两秒同步 WorldGuard，定义区域内禁止放置和拆除方块，其余交互保持默认行为。省略则元数据保存在服务端数据目录。
- `setDataVolume(name)` / `setSavePath(path)`：选择命名卷或宿主机数据目录。命名卷在独立 Compose 中使用 `getVolumes()`，SEED 中调用 `registerVolumes(compiler)`。
- `setOperators(names)`：按大小写敏感的离线用户名计算 UUID，合并到 OP 列表。默认不指定管理员。
- `configureApplication(environment)`：覆盖内存、MOTD、难度等设置；版本、离线模式、内部端口、存档导入由 Bundle 管理。
- `enableHostAccess(port)`：开放宿主机所有接口上的端口；未调用则不映射端口。

默认 `EULA=TRUE`、离线模式、生存模式、easy 难度、2G Java 内存、内部端口 25565。启用服务表示接受 Minecraft EULA。世界数据独立于构建目录，删除命名卷会删除存档。

SemanticRegions 命令及地图查询的使用示例见 E17 README；agent 对地图的只读挂载由实验自行配置。
