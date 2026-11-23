# Minecraft Mindcraft

使用 E17 自定义的小型 SEED 网络，运行 Paper Minecraft、Mindcraft agent **Alice、Bob** 和 PaymentBundle，包含模拟路由、InternetMap 与公网出口。
使用重建后的 `MinecraftAgentService` 生成 Mindcraft 容器；不依赖 `AgentService`、LangGraph 或原有 Minecraft 工具桥接。

- Minecraft Java **1.21.6**，Paper，Java 21，生存模式、简单难度。
- 服务端包含 WorldEdit **7.3.16**、WorldGuard **7.0.14** 和本地 **SemanticRegions** 插件。
- Mindcraft 固定提交 `e1c1fc3ffa481506c2445fc639e16dba504b5920`。
- Alice、Bob 从 AS171 经模拟网络连接 AS170 的 `minecraft.com:25565`。
- 宿主机入服地址：`localhost:25566`，客户端选择 Java 1.21.6。
- Mindcraft 原生界面：<http://localhost:18090>。
- 从本实验 `world/` 目录导入存档，包含独立支付服务，不增加其他 agent 或社交服务。

## 本地世界存档

将 Java 1.21.6 存档放到 `world/`：可以直接包含 `level.dat`，也可以是
`world/存档名称/level.dat`。子目录模式必须只有一份存档，否则生成器报错，避免选错世界。
源目录只读挂载到 `/world-source`，镜像首次启动将其复制到数据卷 `/data/imported_world`。
Paper 自动处理存档内的下界和末地目录。

后续启动继续使用 `imported_world` 的现有进度，不会从源目录重新覆盖。
游玩进度保存在 Docker 数据卷，不写回 `world/`。修改源存档也不会自动重置已有世界。
旧的 `/data/world`、`world_nether`、`world_the_end` 保留；没有删除或覆盖。
如果要再次换存档，应停服并备份当前三个 `imported_world*` 目录后再移走它们，再启动导入。
旧世界的 `map/regions` 标注和 Alice 记忆不会自动转换；切换地图后应核对或重新标注。

## 生成和启动

在 `emuvista` 仓库根目录执行：

```bash
.venv/bin/python experiments/E17_minecraft_mindcraft/experiment.py
```

首次生成会创建权限为 `0600` 的独立 `.env`，不会复制其他实验密钥。
编辑 `experiments/E17_minecraft_mindcraft/.env`，填写模型 API key、聊天地址和模型名。
`LLM_BASE_URL` 应包含接口的 `/v1` 前缀（以你的服务实际要求为准）。
已禁用 embeddings，不需要嵌入模型或 `/embeddings` 接口。
对话/代码示例和技能文档使用本地关键词匹配；`gpt-oss-120b` 可作为聊天模型，
`LLM_MODEL` 使用服务商实际提供的模型 ID。旧的 `EMBEDDING_*` 配置不再生效。
容器中的 `localhost` 指 Alice 容器，不能用它指向宿主机模型服务。

```bash
cd experiments/E17_minecraft_mindcraft/output
for image in dummies/*; do
  docker build -f "$image" -t "${image##*/}" . || break
done
docker compose build
docker compose up -d --remove-orphans
docker compose logs -f minecraft alice
```

从旧 mini Internet 配置迁移时，先在 output 执行 `docker compose down --remove-orphans`，
再按上面的命令启动；不要加 `-v`，这样保留世界和 Alice 记忆。

首次启动服务器需要联网下载 MC；Alice 会等待服务器健康后启动。
使用原版客户端连接后，可以通过游戏聊天或 Mindcraft 界面与 Alice 交流。
首次启用时 Alice 根据人设观察并选择目标；暂停或停止的状态仍需明确恢复。
重启时恢复上游保存的记忆及目标，因此可能继续此前活动。

默认不开启视觉和动态代码生成。需要 `!newAction` 自定义行为/代码建造时，将
`.env` 中 `MINDCRAFT_ALLOW_CODING=true`，然后执行 `docker compose up -d --force-recreate alice`。
这启用的是上游模型代码执行功能；Alice 不授予 OP，也不启用 cheat，施工仍受生存条件限制。

停止：`docker compose down`。世界卷 `mindcraft-world` 和 Alice 记忆卷
`mindcraft-alice` 会保留；`docker compose down -v` 会删除它们。
重新生成 output 不会清空这两个卷。可用 `--host-port` / `--ui-port` 更改入服和界面端口。
上述是新部署的卷名；重新生成时会复用旧配置中的物理卷名，避免名称调整后丢失存档。

## 在游戏里标注建筑与区域

插件保存区域语义，并将边界同步至 WorldGuard。只禁止区域内拆除和放置方块，不主动修改世界方块，不接入其他 agent 框架。
需要玩家拥有 OP 或 `semantic.admin` 权限，以及 WorldEdit 选区权限；不给 Alice 自动授予 OP。
管理员可以执行 `docker compose exec minecraft rcon-cli op 玩家名`。

```text
//wand
```

用木斧左键、右键选中建筑的两个对角（注意包含建筑高度），然后：

```text
/semantic save alice_home residence Alice的家
/semantic describe alice_home Alice的住所，一楼用于存放生活物资
```

站在门口，再执行：

```text
/semantic entrance alice_home
```

每条修改命令完成后自动写入 `map/regions/alice_home.json`。
宿主机目录绑定到容器 `/data/plugins/SemanticRegions/regions`，独立于 output 和世界卷。
该文件同时是持久化存储和导出结果，采用原子替换；外部程序可直接读取，不需要再执行导出命令。
ID 全局唯一，只允许小写英文、数字、下划线、连字符，长度不超过 64，首位为英文或数字。
名称和描述支持中文及空格。重复 save 会报错，避免覆盖已有区域。

其他操作：

```text
/semantic list
/semantic info alice_home
/semantic rename alice_home 新的名称
/semantic type alice_home warehouse
/semantic reselect alice_home
/semantic clearentrance alice_home
/semantic delete alice_home
```

`reselect` 用当前 WorldEdit 选区更新边界，保留其他元数据；必须处于同一世界。
`delete` 只删除标注 JSON，不拆除建筑。多边形使用 `//sel poly` 选区，然后按相同步骤保存；
插件保存完整 x/z 顶点和 min/max 高度，不会仅导出包围盒。其他选区形状会被明确拒绝。

JSON schema v1 的字段：

| 字段 | 含义 |
| --- | --- |
| `schema_version`, `id`, `name`, `type`, `description` | 格式版本、唯一 ID、人工语义标注 |
| `world`, `world_uuid`, `dimension` | 世界名、世界 UUID、维度；用 UUID 区分同维度的多个世界 |
| `geometry.shape` | `cuboid` 或 `polygon` |
| `geometry.min`, `geometry.max` | 绝对方块坐标 `{x,y,z}`，边界包含两端 |
| `geometry.points` | 多边形 `{x,z}` 顶点；长方体为空列表 |
| `entrance` | 未标记时为 null，否则为 `{position:{x,y,z},yaw}`；坐标为玩家脚部所在方块 |
| `created_by`, `created_at`, `updated_at` | 创建玩家 UUID、UTC 时间 |

这是人工标注的区域地图，不包含每个方块、箱子库存，也不会随建筑拆改自动推断新边界。
建筑本体可另用 WorldEdit 的 `//copy`、`//schem save 名称` 保存。
Alice 通过只读挂载 `/map/regions` 读取这些 JSON，使用 Mindcraft 原生命令：

```text
!listRegions
!getRegion("house_01")
```

也可以直接对 Alice 说“查询 house_01，告诉我房子的范围和入口”。
每次查询重新读文件，游戏内保存后无需重启 Alice；删除区域也会在下次查询生效。
列表最多返回 100 条，详情按 ID 查询。损坏的文件会返回错误，不会终止 agent。
这不是自动推送：保存不会主动打断 Alice，提示她“标注已更新，请重新查询”即可。
区域信息是人工标注，不保证实时方块状态或路径可通行；入口未标记时返回 null。

## 从原服务端迁移

服务端从 Vanilla 改为 Paper，保留 Minecraft 版本和现有数据卷。
在 Docker 可用时，先停止旧服务并备份世界卷，再启动新配置。
生成器在 Compose 项目名称变化时会保存 `.runtime/previous-deployment.yml`；
存在该文件时，在当前实验目录执行：

```bash
docker compose -f .runtime/previous-deployment.yml down
```

不要加 `-v`。然后在 output 中执行 `docker compose build` 和 `docker compose up -d`。
因为 Alice 的启动脚本路径也已清理，首次迁移需同时重建 Alice。
Paper 会调整维度的存储布局；如需退回 Vanilla，应恢复迁移前的备份。

插件单独构建（Java 21、Maven）：

```bash
cd server
mvn package
```

产物为 `target/semantic-regions.jar`。Docker 构建会执行同样的编译与测试，
并把插件和固定版本的 WorldEdit 放入服务端镜像。

## 实现边界

### 人设驱动的自主行动

`experiment.py` 的 `PERSONAS` 保存 Alice、Bob 的身份、习惯、偏好及行为边界，不再提供 task_id 或 goal。
模型通过工具观察游戏状态，然后调用 `!chooseGoal("目标", "观察依据、动机和完成条件")` 记录自行选择的目标。
执行后通过 `!endGoal` 自报完成，等待一段时间后重新观察；无必要行动时可调用 `!waitForSituation("理由")`。
人设引导行为，不保证一定生成回家睡觉等特定任务。

- `persona`：长期人设，注入 Mindcraft profile 和自主决策提示。
- `auto_start`：首次启用时自动开始观察与选择目标。
- `resume_on_restart`：恢复运行中或等待中的自主循环；不恢复明确暂停、停止或失败的循环。
- `cooldown_ms`：执行循环冷却，最小 2000 毫秒。
- `decision_interval_ms`：完成或等待后再次决策的间隔，最小 30000 毫秒，当前为 60000。

控制命令保持 `!startTask`、`!taskStatus`、`!pauseTask`、`!resumeTask`、`!stopTask`。
启动命令现在表示启用人设自主行动。手动 `!goal` 完成后仍停止，不自动转为人设目标。
旧预设任务不会自动恢复；旧暂停和停止状态保留，需明确恢复。
`autonomy-state.json` 保存当前阶段、目标和最近结果；同目录 `autonomy-state.json.events.jsonl` 记录目标、理由及状态变化。
完成记录是模型自报，工具观察与执行细节仍需查原生对话日志。
修改 `PERSONAS` 后重新运行 `experiment.py`，再重新创建 agent 容器以刷新 profile，无需重建镜像。`output/personas/*.json` 是自动生成的运行时配置，不需要手动维护。

`experiment.py` 生成三个服务的 Compose 配置及构建目录，`configure.mjs` 只生成原生配置，
随后直接运行上游 `node main.js`。`patch_mindcraft.py` 在构建时对固定上游提交
做局部适配：支持 `embedding: false`，不创建嵌入客户端，并修复无嵌入时的技能文档
关键词检索和全量文档返回。示例检索使用上游已有的关键词匹配，agent 循环仍由上游管理。
上游 MindServer 仅监听容器内 localhost，启动脚本用 socat 将容器 8081 转发到
localhost:8080，再映射到宿主机回环地址 18090；端口转发不修改上游源码。
Docker 构建采用上游原生依赖并执行 `npm install`；上游提交未提供 lockfile，
因此只固定了 Mindcraft 源码，npm 间接依赖和基础镜像并非完全锁定。

来源：[Mindcraft](https://github.com/mindcraft-bots/mindcraft/tree/e1c1fc3ffa481506c2445fc639e16dba504b5920)。

## Bob

Bob 使用同一份 Mindcraft 构建源码，通过 `AGENT_NAME=Bob` 设置身份。
镜像为 `output-bob`，容器为 `mindcraft-bob`；独立记忆卷 `mindcraft-bob` 挂载到 `/app/bots/Bob`。
两人的人设统一配置在 `experiment.py` 的 `PERSONAS` 中，两者都只读访问区域地图。
Bob 的界面为 http://localhost:18091，可用 `--bob-ui-port` 修改；Alice 界面仍为 18090。
两个容器的 MindServer 独立，彼此忽略对方的公开聊天，避免自动对话循环。
单独控制某人可以用游戏内私聊 `/msg Bob !taskStatus`、`/msg Alice !pauseTask`；
公开聊天中的任务控制命令可能被两人同时接收。
Bob 的人设重视私人空间和规律作息，是否回家休息由它结合观察自行决定。

## 区域保护同步

`map/regions/*.json` 是保护边界的来源。启动时同步，游戏内 `/semantic` 修改后立即同步，
直接修改文件后约 2 秒同步；删掉 JSON 会解除该区域保护。可执行 `/semantic sync` 强制同步。
长方体和多边形均按原始边界处理。WorldGuard 内使用保留前缀 `semantic_`，例如
`semantic_alice_house`。请通过 JSON 或 `/semantic` 修改这些区域，不要手动维护同前缀的 WorldGuard 区域。
其他名称的 WorldGuard 区域不受同步器管理。

同步只设置三个标志：`passthrough: allow`（关闭默认领地成员限制）、
`block-break: deny`、`block-place: deny`。不开启禁入、防爆、防火或箱子权限规则；
开门、睡觉、使用容器等仍按原版规则。WorldGuard 的 OP/bypass 权限仍有效，
`seed` 作为 OP 默认可以绕过保护；Alice/Bob 没有 OP。

按 JSON 的 `world` 名称和 `dimension` 定位世界。导入同一世界产生不同 UUID 时记录警告，
仍按世界名与维度应用边界；换成不同地图时请重新圈选，避免旧坐标保护到错误位置。
文件格式、边界或目标世界验证失败时，整轮同步停止并保留上一次保护，错误写入服务器日志。

查看同步结果：

```text
/semantic sync
/rg info semantic_alice_house
/rg info semantic_bob_house
```

服务端由公共 `bundles/MinecraftBundle` 生成，构建文件与插件源码位于该 Bundle 的 `server/`。实验仅配置存档、语义地图、端口和离线管理员；生成后的构建上下文仍为 `output/server`，镜像名仍由 Compose 生成（`output-minecraft`）。

Mindcraft 构建与运行时代码统一维护在 `services/MinecraftAgentService/runtime/`。E17 仅保留角色、人设、凭据、地图和部署配置；修改公共运行时代码后重新生成 output 并重建对应 agent 镜像。

## mini Internet 和支付服务

网络配置位于 `experiment.py`，直接创建 Base、Routing 和 Ebgp 层，再 render 和 compile；不加载 B02 示例。应用容器仅挂在各自 SEED 子网，默认路由指向该 AS 的路由器；AS99999 提供公网出口。Minecraft/Mindcraft 保留 Docker 公网 DNS 以解析模型及下载域名，并映射模拟域名；Payment 容器也配置实验域名映射，无独立 DNS 容器。

| 服务 | 模拟网络地址 | 宿主机入口 |
| --- | --- | --- |
| Minecraft | AS170 / 10.170.0.10 | localhost:25566 |
| Alice | AS171 / 10.171.0.10 | http://localhost:18090 |
| Bob | AS171 / 10.171.0.11 | http://localhost:18091 |
| Payment | AS150 / 10.150.0.10–23 | http://localhost:8443 |
| InternetMap | SEED 地图组件 | http://localhost:8080（地理地图 8082） |

Payment 默认端口可用 `--payment-port` 设置。支付账户和初始余额在 `experiment.py` 的 `PAYMENT_CONFIGURATION` 中维护，目前 Alice、Bob 均为 100 MC；登录邮箱分别为 `alice@mail.com`、`bob@mail.com`，演示密码为 `payment-demo`。这只初始化账户，Mindcraft 尚未接入支付工具。

支付状态保存在实验目录 `.runtime/payment-state/`，重生成 output 不删除状态；已有状态上的初始化变更遵循 PaymentBundle 的初始化规则。世界、Alice 和 Bob 的原有命名卷继续复用。人设仍统一在 `experiment.py` 的 `PERSONAS` 中维护。

首次运行先按上文构建 `dummies` 基础镜像，再构建完整 Compose。拓扑由 3 个业务 AS、1 个出口 AS 和 1 个交换网络组成，每个 AS 一台路由器，无额外演示主机或路由服务器；启动使用完整的 `docker compose up -d`；只启动三个游戏容器不足以运行模拟网络。不要同时运行占用相同 SEED 子网或路由容器名称的其他实验。
