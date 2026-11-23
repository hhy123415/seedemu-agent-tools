# H40 — Evennia

在 H40 内独立构建精简网络，不导入或修改 `H00_mini_internet`。
保留两个 AS、一个交换中心、DNS、外网出口和 InternetMap。
业务应用仅有 Evennia；SQLite 在同一应用容器中运行。

```text
AS99999：internet-egress（外网出口，10.100.0.99）
└── IX100：10.100.0.0/24（eBGP 直连，无路由服务器）
    └── AS150：router0（10.100.0.150）
        └── net0：10.150.0.0/24（网关 10.150.0.254）
            ├── Evennia：10.150.0.10（evennia.com）
            ├── 权威 DNS：10.150.0.53（根、com、evennia.com）
            └── 递归 DNS：10.150.0.54
```

生成结果为 11 个 Compose 服务、4 个网络，其中包括 4 个 InternetMap 服务和
2 个基础镜像辅助服务。相比之前的完整拓扑（116 个服务），移除了企业园区和
无关主机、骨干 AS。每个 AS 只有一台路由器，无需 iBGP 和 OSPF。

Evennia 使用解析器 `10.150.0.54`；模拟网络内可通过
`http://evennia.com:4001/` 或 `http://10.150.0.10:4001/` 访问。
宿主机仍使用下面的 localhost 地址，不依赖宿主机解析 `evennia.com`。
外网出口发布两条 `/1` 路由；DNS 使用模拟根区，不提供完整的公网域名解析。

在 emuvista 目录执行：

```bash
.venv/bin/python examples/H40_evennia/evennia.py
cd examples/H40_evennia/output
docker compose up -d --build
docker compose ps
docker compose logs -f evennia
```

网页：<http://localhost:4001/>，游戏：<http://localhost:4001/webclient/>。
初始管理员：`admin`，密码：`emuvista`（已有世界仍使用原来的密码）。
端口仅绑定本机；Telnet 为 `localhost:4000`，WebSocket 为 `localhost:4002`。

Bundle 可以直接配置启动时导入地图，H40 默认如下：

```python
bundle = (EvenniaBundle(emu, name='evennia')
          .setDataVolume('h40-evennia-data')
          .setSuperuser('admin', 'emuvista')
          .importMap(HERE / 'school-map.json', mode='replace', spawn='gate')
          .enableHostAccess(web_port=4001, websocket_port=4002, telnet_port=4000))
```

`mode='append'`（默认）保留现有地图并追加；`mode='replace'` 替换现有地图，
必须用 `spawn` 指定 JSON 中可站立地点的 `key`。这里用校门口 `gate` 复用
默认出生点（原 Limbo），已有角色和物品安置到这里，账号和背包保留。
**已有数据卷第一次使用这项配置时也会执行替换。**

地图在生成构建目录时校验并打包，服务器完成初始化后导入。
相同地图内容和导入参数在同一数据卷中只执行一次，重启或重新构建不会
覆盖编辑器中的修改；修改地图内容或导入参数后，重新生成、构建并启动
Evennia 会执行新的导入。删除数据卷后会重新执行。
不需要自动导入时移除 `.importMap(...)`；运行中手动导入仍使用网页编辑器。

InternetMap：拓扑页面 <http://localhost:8080/>，地理页面
<http://localhost:8082/>；抓包服务端口为 `8081`。这些端口在 H40 中硬编码。
InternetMap 展示网络节点；Evennia 地点编辑器仍位于 `/topology/`。

默认使用命名卷 `h40-evennia-data`。停止后再启动保留账号、游戏代码和世界状态：

```bash
docker compose down
docker compose up -d
```

不要用 `down -v`，除非确实要删除世界重新初始化。重新运行生成脚本不会清空卷。
可通过 `docker compose exec evennia sh` 进入容器，在 `/data/game` 下使用
Evennia 管理命令或编辑游戏项目。

Compose 不指定项目名，默认采用输出目录名 `output`；Evennia 服务和容器名为
`evennia`。从旧的 `h40-evennia` 项目更新时，先在旧配置目录执行
`docker compose -p h40-evennia down`（不加 `-v`），再重新生成并启动。
数据卷仍使用 `h40-evennia-data`，以继续使用已有世界。

从完整 mini_internet 切换到精简版时，先用旧配置执行 `docker compose down`
（不加 `-v`），再重新生成配置并构建、启动，避免旧拓扑节点和网络残留。

可选：指定持久化目录：

```bash
.venv/bin/python examples/H40_evennia/evennia.py \
  --state "$PWD/examples/H40_evennia/state"
```

端口在 `evennia.py` 中固定为 HTTP 4001、WebSocket 4002、Telnet 4000。
`--state` 与 `--output` 必须互不包含。
镜像构建需要下载 Python 基础镜像和依赖；使用固定的 Evennia 5.0.1。

## 分层地图编辑

使用当前管理员账号登录后，打开 <http://localhost:4001/topology/>。
地图直接编辑持久化世界；新部署不会自动创建演示学校。

[school-map.json](school-map.json) 保存学校示例的地点、入口和双向通路设计：
学校下包含校门口、校园广场、教学楼、图书馆、操场和食堂；教学楼包含门厅、
101–103 教室和教师办公室，图书馆包含大厅、阅览室和书库。创建时将原 Limbo
改名为校门口并保留其对象编号，以保持角色位置和默认出生点引用。
这个文件用于记录地图设计，不会在容器启动时自动覆盖已有世界。

可以按以下顺序建立：

```text
世界
├── 学校（区域，入口：校门口）
│   ├── 校门口（可站立地点）
│   ├── 操场（可站立地点）
│   └── 教学楼（区域，入口：门厅）
│       ├── 门厅（可站立地点）
│       ├── 一班教室（可站立地点）
│       └── 二班教室（可站立地点）
└── 住宅（区域，入口：住宅门口）
    └── 住宅门口（可站立地点）
```

1. 顶层新建“学校”，类型选择“区域”。选中后点击“进入内部”。
2. 新建“校门口”，类型选择“可站立地点”；同样建立操场、教学楼及其内部地点。
3. 用面包屑回到顶层，选中学校，将“进入区域时到达”设置为校门口并保存。
4. 创建出口，例如“住宅门口 → 学校”，名称为“进入学校”。游戏角色使用这个出口
   会到达校门口。教学楼同理，先指定门厅，再建立“校门口 → 教学楼”的出口。

点击节点查看并编辑属性，点击“进入内部”或节点右下角的箭头逐层展开。
面包屑和“上一层”用于返回。拖动节点后点击“保存布局”。

已有 H40 需要重新生成配置、构建镜像并重建服务后才能加载编辑器。
重建时保留 `h40-evennia-data` 数据卷和已有管理员密码，不需要清空世界。

工具栏提供“导出地图”和“导入地图”。可直接选择本例的 `school-map.json`，
校验通过后可选择“追加”或“替换”：追加保留原地图，重复导入会创建副本；
替换会移除原地图，需选择新地图中的可站立地点安置角色和物品。
替换学校地图时，可选择“校门口”，它会复用原默认出生点编号。
替换前会显示影响数量，勾选确认后执行；账号、角色及背包内容保留。
导出文件不含节点排版 `position`，只包含地图结构和描述，导入后自动布局。

进入教室后可点击“新建物品”，设置名称、描述和是否允许拾取。物品会以紫色
节点显示在该房间里，可编辑、移动到其他房间或删除。游戏内使用 `look`、
`get`、`drop` 与物品交互；专用使用动作暂未配置。物品持久化在数据卷中，
目前地图 JSON 导入导出不包含物品。
