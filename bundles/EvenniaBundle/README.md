# EvenniaBundle

单容器 Evennia 世界：Portal、Server、Web 和 SQLite 在同一容器运行。
固定使用 `evennia==5.0.1`、Python 3.11；当前工作区已有的 Evennia 环境也是此版本。
首次启动创建默认游戏目录、迁移数据库并初始化管理员。整个 `/data` 持久化，
其中 `game/server/evennia.db3` 保存世界数据，`game/` 保存游戏代码和日志。

## 独立运行

参考 [H40](../../examples/H40_evennia/README.md)。`prepare(output)` 返回单个
Compose service 配置，调用方还需在 Compose 根级声明 `getVolumes()`。
默认不发布端口，调用 `enableHostAccess()` 后只绑定宿主机 `127.0.0.1`。

## 接入 SEED

在拓扑已经创建并 `emu.render()` 后：

```python
from bundles.EvenniaBundle import EvenniaBundle

world = (EvenniaBundle(emu)
         .setSuperuser('admin', 'your-password')
         .setDataVolume('evennia-data')
         .enableHostAccess())
# 地址和网关由实验拓扑提供。
world.addInternalNetwork('150', 'net0', ['10.150.0.10'], '10.150.0.254')
world.registerVolumes(compiler)
compiler.addContainerBundle(world)
emu.compile(compiler, output, override=True)
```

`setSavePath(path)` 可替代命名卷，绑定宿主机目录。更换初始化管理员配置不会
修改已有数据库中的账号。游戏使用 Evennia 默认项目，不附带智能体或实验地图。
内部端口为 Telnet 4000、HTTP 4001、WebSocket 4002。
`enableHostAccess(web_port, websocket_port, telnet_port)` 支持更改宿主机端口，
并配置网页客户端使用对应的 WebSocket 外部端口。

启动参考：[官方 Docker 文档](https://www.evennia.com/docs/latest/Setup/Installation-Docker.html)。

## 分层地图编辑器

管理员登录后访问 `/topology/`。编辑器与游戏共用 Evennia Server 和数据库，
支持创建、改名、描述、归属调整、空地点删除、真实出口编辑和持久化拖动布局。

- **区域**：用来组织学校、教学楼等空间层级，本身不能容纳角色或物品。
- **可站立地点**：校门口、门厅、教室等真实游戏房间。
- **入口**：区域内部的一个可站立地点。通向区域的出口实际指向入口；
  修改区域入口后，编辑器创建的这类出口同步更新。
- **归属与通行**：保存归属不会自动创建出口；出口可跨层连接。双向通路由两个
  独立出口组成，之后分别编辑。更换入口不会自动搬移原入口的返回出口。

数据使用命名空间 `topology_editor` 下的 Evennia Attributes：房间的 `parent`、
区域的 `entry`、房间的 `position`，以及出口的 `area_target`。区域类型为
`topology_editor.rooms.Area`。原有普通房间显示在顶层，原有出口保持不变。
在顶层，图上的箭头可以汇总内部地点间的跨区域通路；右侧显示实际起终点。

编辑仅允许已登录且启用的 staff 账号，写请求校验 CSRF 和地图版本。不能制造
循环归属、把入口移出区域，或删除仍被引用、仍有内部地点或内容的房间。

镜像启动时把 Bundle 管理的 `topology_editor/` 包同步到持久化游戏目录，幂等地
向 `web/urls.py` 注册路由，不覆盖原有 URL 配置。修改扩展应在 Bundle 源码中完成。
更新已有部署需要重新构建镜像并重建 Evennia 容器，原数据卷保留。

测试使用独立测试数据库，在已安装扩展的游戏目录中运行：

```bash
evennia test topology_editor.tests --settings settings --noinput
```

## 房间物品编辑

进入教室等可站立地点后，图中用紫色节点显示直接放在房间里的物品。
点击“新建物品”可创建真实 Evennia 对象；单击物品编辑名称、描述、所属地点
和“允许角色拾取”，也可拖动排版或删除。区域不能直接放置物品。
游戏中使用 `look 物品名` 查看、`get 物品名` 拾取、`drop 物品名` 放下。
取消可拾取后是固定陈设，普通角色不能拿走；管理员可能绕过权限锁。
这项设置管理物品的 `get` 锁；不提供坐下、开关或使用电脑等专用动作。

角色和角色背包不显示在物品编辑中；物品被拿走或放下后点击“刷新”同步。
有内部内容或被其他对象的 home/destination 引用的物品不能删除。
物品保存在世界数据库中，当前地图 JSON 导入导出仍只处理地点和出口，
不包含物品。替换地图时，原有地面物品沿用现有规则迁移到安置地点。

## 地图导入与导出

也可在 Bundle 链式配置中调用 `importMap(path, mode='append', spawn=None)`，
将本地 JSON 校验并打包到镜像，服务器启动后自动导入。例如：

```python
world.importMap('school-map.json', mode='replace', spawn='gate')
```

`append` 保留原地图；`replace` 必须指定 JSON 中可站立地点的 key 作为 `spawn`。
替换适用于已有数据卷，也会移除其旧地图。同一地图内容及参数在同一个世界中
只自动执行一次，标记保存在数据库中；重启不覆盖后续手动编辑。
修改内容或参数后需重新生成、构建并启动容器，会执行新的导入。
移除该调用可关闭自动导入；导入失败不记录完成标记。

编辑器工具栏的“导出地图”下载整个世界已保存的地图 JSON；“导入地图”选择
JSON 文件后先校验并预览数量，选择导入方式：

- **追加**：在世界顶层添加新地图，原地图、角色和出生点引用不变；重复导入产生副本。
- **替换**：移除原地图及关联出口，以文件中的地图替代。需指定一个可站立地点，
  用于安置旧地图中的角色和地面物品，并更新回家引用及离线角色的下线位置。
  背包内容、账号和角色保留。确认框显示替换数量，需要勾选确认后执行。

替换会复用当前默认出生房间的对象编号，将其改为所选安置地点，避免配置中的
`DEFAULT_HOME`、`START_LOCATION` 失效。两项配置须指向同一个有效普通房间，
否则预览会拒绝替换。游戏自定义属性中的任意地点引用不在自动迁移范围内。
导入为一个数据库事务，失败会回滚，并恢复相关 Evennia 对象缓存。

格式为 `emuvista.evennia.map`，`version: 1`：`nodes` 保存可移植的 key、名称、
描述、类型、父地点和区域入口，`connections` 保存出口名称及起终点 key。
不保存编辑器排版 `position`，导入后自动布局；兼容旧文件中的 position 但忽略它。
兼容 H40 的 `school-map.json` 和其中的 `reverse_name` 双向通路写法。
`reuse_limbo` 不参与导入；替换模式的默认房间复用由界面选择的安置地点决定。

这是地图结构交换格式，不是完整世界数据库备份：不包含账号、角色、物品、
自定义类型类、锁、出口别名或其他游戏属性。文件最大 1 MB，最多 1000 个地点、3000 条 connections。
