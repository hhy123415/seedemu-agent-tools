# MinecraftAgentService

基于 E17 提取的 Mindcraft 容器服务。新版不继承项目的 AgentService，也不包含旧 LangChain 扩展、HTTP 工具桥接或自建 Mineflayer runtime；agent 循环和游戏行为由 Mindcraft 执行。

这是独立 Compose 服务生成接口，不是旧版 SEED `Service.install(vnode)` 接口。E17 保持普通 Docker 网络。

```python
from services.MinecraftAgentService import MinecraftAgentService

agents = (MinecraftAgentService('.env', minecraft_host='minecraft', minecraft_version='1.21.6')
          .setRegionPath('map/regions')
          .addAgent('Alice', persona_file='persona.alice.json', ui_port=18090)
          .addAgent('Bob', persona_file='persona.bob.json', ui_port=18091))
compose = agents.prepare('output', context_name='alice', minecraft_service='minecraft')
```

返回 `services` 和 `volumes` 字典，调用方合并 MinecraftBundle 的服务后写入 Compose YAML。连接外部 Minecraft 服务器时省略 `minecraft_service`，不生成本地健康依赖。

每个角色单独拥有容器、记忆卷和人设文件，共享构建上下文。默认 Compose 服务名为角色名小写，容器和数据卷为 `mindcraft-<服务名>`；可通过 `addAgent` 参数覆盖。界面端口可选且仅绑定宿主机回环地址。角色名支持 1–16 位字母、数字和下划线。名字、服务名、容器、数据卷、界面端口必须独立。

## Runtime

`runtime/Dockerfile` 固定 Mindcraft 提交 `e1c1fc3ffa481506c2445fc639e16dba504b5920`，沿用 Node 22 构建环境。

- `configure.mjs`：生成原生 profile/settings，默认禁用 embedding，使用中文交流。
- `patch_mindcraft.py`：禁用嵌入调用并使用关键词检索。
- `autonomy.mjs` / `patch_autonomy.py`：基于原生 SelfPrompter 的任务启动、暂停、恢复、停止和完成状态；状态随每个角色的数据卷持久化。
- `region_queries.mjs` / `patch_region_queries.py`：通过 `!listRegions` 和 `!getRegion` 读取最新地图标注。
- `start.sh`：配置后启动 Mindcraft `main.js`，提供 UI 转发。

`.env` 通过 Compose 在运行时注入，不复制进镜像。支持 `OPENAI_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL`、`MINDCRAFT_ALLOW_CODING`。同组其他角色自动加入公开聊天忽略名单，沿用 E17 防止机器人相互触发聊天循环的行为。

人设 JSON 与 map 由实验维护，只读挂载到 agent。人设不包含固定任务，例如：

```json
{"persona":"A resident who values privacy and a regular daily routine.","auto_start":true,"resume_on_restart":true,"cooldown_ms":5000,"decision_interval_ms":60000}
```

更新代码后需重新生成 Compose 并重建 agent 镜像；更新地图后查询可直接读到新数据。任务操作使用 `!startTask`、`!taskStatus`、`!pauseTask`、`!resumeTask`、`!stopTask`；完成由 Mindcraft 调用 `!endGoal`。

模型观察后使用 `!chooseGoal` 记录自行生成的目标和理由。`!endGoal` 完成人设目标后延迟重新决策，`!waitForSituation` 允许等待；暂停和停止仍需明确恢复。旧固定任务不会自动恢复。修改人设后重新创建 agent 容器以刷新 profile。
