# H11：浏览器与 Agent 同容器

包含 H10 完整域名服务，通过 `Docker.attachCustomContainer()` 添加独立
`browser-agent` 容器，接入 AS154/net0，IP 为 `10.154.0.80`。
不覆盖现有 SeedEmu Host。镜像安装 Chromium、Playwright、Xvfb、只读 VNC 和
本示例 `agent/` 目录中的源码，agent 和浏览器都在容器内运行。

在本目录使用已安装 SeedEmu 的 Python 环境执行：

```bash
python browser_agent.py
cd output
docker compose build
docker compose up -d
cd ..
python setup.py
```

Agent 网页：<http://localhost:18089/>，网页内可查看实时浏览器画面。
FOSSBilling 普通入口仍为 <http://localhost:18080/>，管理员入口为
<http://localhost:18080/admin>，Registry 为 <http://localhost:18081/>。
Agent 内访问业务网站使用仿真 IP（例如 `http://10.150.0.72:8080/`），
容器内 localhost 指向容器自身。

浏览器控制、VNC 和 noVNC 静态文件仅监听容器 loopback；只向宿主机 localhost
映射 agent 的 18089 端口。`agent/local_tools/dns/tools.py` 直接运行本容器的 `dig`，
不需要 Docker socket。agent 的源码和依赖清单均位于本示例的 `agent/` 目录。

## 模型 API 与网络

网页中填写 API 地址、密钥和模型。构建只复制明确列出的源码文件与 Python 包，
同时复制 `agent/model_profiles.json`（如果存在）；不复制 `.env` 或运行缓存。
该配置包含 API Key，已加入本示例 `.gitignore`；构建上下文和镜像也可能包含该配置，请勿公开分发。

仿真 `10.0.0.0/8` 流量走 AS154 路由器；默认路由保留 Docker 的外网出口。
默认 DNS 走仿真递归服务器 `10.153.0.53`。需要通过 Docker 出口访问的地址统一填写在
`egress_urls.txt`，每行一个 URL、域名或 IP，不需要填写路由或 DNS 命令，例如：

```text
https://api.example.com/v1
api.other-provider.com
10.13.94.198
```

容器启动时自动读取该文件：域名交给 Docker DNS，位于 `10.0.0.0/8` 的 IP
添加经 Docker 默认网关的 `/32` 路由（本容器的 `10.154.0.0/24` 网段除外）。
普通公网 IP 已由默认路由出网。若域名解析到外部 `10.*` 地址，还需把对应 IP 加入文件。
该文件是出网例外配置，不是限制其他网络访问的防火墙白名单。
API 密钥仍只保存在模型配置中；修改模型地址后，如需出网，应同步更新此地址文件。

首次应用此改动需要重新生成配置并手动构建启动容器。之后修改地址文件，在 H11 目录执行以下命令即可应用，无需重新构建：

```bash
docker compose -f output/docker-compose.yml restart browser-agent
```

该文件以只读方式挂载到 `/opt/network-config/egress_urls.txt`；镜像内也保留一份初始配置。
重启会关闭现有浏览器会话。自定义输出目录时调整命令中的 Compose 文件路径。
宿主机运行模型服务时可使用 `http://host.docker.internal:端口/v1`，
服务须监听容器可访问的地址。此环境不会自动验证模型 API，也不会自动执行 agent 任务。

## 脚本与数据

- `browser_agent.py`：只生成 H11 的 Docker 部署文件，不构建或启动容器。
- `container/prepare_context.py`：准备 Docker 构建上下文，由入口编译后调用。
- `setup.py`：等待 H10 服务自动初始化，完成跨容器配置及验证，再验证 agent HTTP 和 Playwright 实际连接。
- 清理：`docker compose -f output/docker-compose.yml down --remove-orphans --volumes`，删除容器、网络及项目卷；自定义输出目录需替换配置路径。
- 构建和初始化均支持 `--output`；构建支持 `--platform`。

H10/H11 默认都使用 Compose 项目 `output`，业务端口也相同，应作为替代场景运行，
不应同时启动。切换时可先执行 `docker compose -f output/docker-compose.yml down --remove-orphans --volumes` 清理旧部署，这会删除其数据库数据。
H11 不会自动清理旧场景。模型配置保存于宿主机 `agent/model_profiles.json`，重建和清理 均不会删除这份文件。

生成的构建上下文位于 `output/browser-agent`，修改本示例 `agent/` 源码后重新运行 `python browser_agent.py`，再进入 `output` 手动构建并启动才会更新容器。
浏览器与 agent 依赖版本以 `agent/requirements.txt` 为准。

模型 API Key 仅来自网页填写和宿主机 `agent/model_profiles.json`。
构建将配置复制到 `/opt/agent/model_profiles.json`；运行时将宿主机 `agent/` 目录挂载到
`/opt/agent-config`，后端优先读写 `/opt/agent-config/model_profiles.json`，支持原子保存。
浏览器、DNS 工具固定在当前容器执行，网页和工具均不接受可切换的 source。
首次打开填写配置后点击“保存配置”，后续打开从该文件加载；不读取 `local_config.json`、
环境变量或浏览器 localStorage。未保存的输入仅保留在当前页面内存中，刷新会丢失。

## 重新启动 Agent

容器仍沿用原有入口自动启动浏览器与 agent。进程退出后，在 H11 目录执行：

```bash
python start.py
```

该脚本执行 `docker compose restart browser-agent`，可以重新启动已停止的容器，
也可以重启正在运行的容器；不会重建镜像或重新初始化域名服务。
支持 `--output` 指定已有 Compose 配置目录。首次部署或清理容器后需先生成配置，并在 `output` 中手动构建和启动容器。
重启会关闭当前浏览器会话，已保存的 `model_profiles.json` 保留；刷新网页后重新开始对话。

依赖按独立构建层安装，apt、Composer 和 pip 使用 BuildKit 下载缓存。
首次应用安装步骤改动时仍需重建对应层；随后修改 agent 源码或模型配置只影响后续复制层。
镜像构建失败后可在 `output` 中重跑 `docker compose build`，无需清理。共享下载缓存加锁，因此并行构建时可能等待其他安装步骤。

网络配置逻辑位于 `container/start.sh`，镜像内路径为 `/opt/h11/start.sh`。
它在启动 dnsmasq、浏览器和 agent 前读取 `egress_urls.txt`，完成仿真路由、IP 路由例外、
域名 DNS 分流和容器解析器设置。此脚本保留 Docker 默认网关，不输出模型密钥。
修改脚本逻辑后需更新镜像；仅修改地址文件时重启 browser-agent 即可。
