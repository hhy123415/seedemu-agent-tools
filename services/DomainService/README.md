# DomainService

DomainService 提供域名注册、客户购买、DNS 托管和模拟支付服务，可组合部署到仿真网络。

| 服务 | 功能 |
| --- | --- |
| `RegistryService` | 注册局、TLD、EPP 注册商接入及父区委派发布 |
| `FossBillingService` | 客户网站、域名商品、订单和账单 |
| `DnsHostingService` | 主从权威 DNS、托管 API 和 DNS 商品 |
| `FakePaymentService` | 模拟收银台和 FOSSBilling 支付网关 |

[H10](../../examples/H10_domain_name_purchase/README.md) 提供完整域名购买环境；
[H11](../../examples/H11_browser_agent/README.md) 增加同容器运行的浏览器和 agent。
H10 使用 `domain_name_purchase.py`、H11 使用 `browser_agent.py` 生成部署文件；进入 `output` 手动构建启动后，再用 `setup.py` 完成跨容器配置及验证。清理命令见各示例说明。

## 使用

使用能够导入 `DomainService` 和 `seedemu` 的 Python 环境。在已创建的模拟器 `emu` 上配置服务：

```python
from DomainService import RegistryService
from seedemu.core import Binding, Filter

registry = RegistryService()
server = registry.install('registry')
server.setTlds(['com', 'net'])
server.setAdminAccount('admin@example.com', '123456')
server.setDatabasePassword('registry-demo-password')
server.setPortForwarding(18081)
emu.addLayer(registry)
emu.addBinding(Binding('registry', filter=Filter(asn=151, nodeName='host_1')))
# 最后统一 emu.render() 和 emu.compile(...)。
# Finally call emu.render() and emu.compile(...).
```

目标主机必须已经存在且不承载冲突的应用。服务在 render 阶段写入安装、配置和启动操作。
`setEppPort(port)` 设置 EPP 监听端口，默认 700；Web 面板监听 8080；宿主机端口通过服务实例的 `setPortForwarding(host_port)` 配置。
显示名可通过 Server 继承的 `setDisplayName()` 修改。

Registry 使用以下配置：固定上游提交、PHP 8.5、`.com`/`.net` 初始化、
本地 MariaDB 和 Redis、管理面板、EPP TLS、DAS，以及每五分钟执行的生命周期任务。
默认仿真参数保留在 `RegistryService/registry_defaults.py`，账号和数据库密码可由每个 Server
独立配置。`setAdminAccount(email, password)` 和 `setDatabasePassword(password)`
设置首次初始化所用凭据，不是运行中数据库账号的密码轮换接口。`setTlds()` 设置首次初始化的 TLD 列表，`getTlds()` 返回列表副本。支持 `com` 或 `.com`，
统一为小写并去重；仅支持单标签 ASCII 名称，国际化名称需传入 Punycode。
受上游数据库字段限制，标签最长 31 字符。列表不能为空。每个 TLD 继承固定上游版本的默认
注册、续费、转移和恢复价格；未指定的上游示例 TLD 不保留。已有数据库不会被迁移。

## 端口映射与网站访问

Registry 和 FOSSBilling 的 Web 端口为 `8080`；FakePayment 的内部端口由 `setPort()` 设置。
通过服务实例的 `setPortForwarding(host_port)` 设置宿主机端口，传入 `None` 禁用映射。
默认宿主机端口分别为 Registry `18081`、FOSSBilling `18080`、FakePayment `18083`。
Registry 和 FOSSBilling 位于不同容器，因此可以使用相同的容器端口，
但映射到同一宿主机时应使用不同的宿主机端口。

H10 示例在入口中配置：

```python
# Registry：宿主机 18081 转发到 Registry 容器 8080。
# Registry: forward host port 18081 to port 8080 in the Registry container.
registry_server.setPortForwarding(18081)

# FOSSBilling：宿主机 18080 转发到 FOSSBilling 容器 8080。
# FOSSBilling: forward host port 18080 to port 8080 in the FOSSBilling container.
registrar.setPortForwarding(18080)
```

上面的两个实例分别属于 Registry 和 FOSSBilling，映射在安装时添加到实际绑定主机。
生成配置、手动构建启动容器并完成 `python setup.py` 后，在运行 Docker 的宿主机浏览器中访问：

| 服务入口 | 访问地址 | 用途 |
| --- | --- | --- |
| Registry 管理面板 | [http://localhost:18081/](http://localhost:18081/) | 管理注册局、TLD 和注册商 |
| FOSSBilling 普通用户入口 | [http://localhost:18080/](http://localhost:18080/) | 客户登录、域名购买、订单与账单 |
| FOSSBilling 管理员入口 | [http://localhost:18080/admin](http://localhost:18080/admin) | 管理客户、TLD 商品、价格及注册商配置 |

FOSSBilling 的普通入口和管理员入口共用 `18080` 端口，通过 URL 路径区分，
不需要为管理员入口额外映射端口。只部署 Registry 场景时，仅提供 Registry 面板。

示例首次初始化的账号如下；如已在入口改过参数，以实际配置为准，已有账号不会因修改默认值自动更新：

| 入口 | 邮箱 | 示例密码 |
| --- | --- | --- |
| Registry 管理员 | `admin@example.com` | `123456` |
| FOSSBilling 普通用户 | `user@example.com` | `Aa123456` |
| FOSSBilling 管理员 | `admin@example.com` | `Aa123456` |

端口映射只负责网络转发，不改写应用生成的链接。FOSSBilling 默认允许
`localhost:18080` 和 `127.0.0.1:18080` 作为浏览器入口；若将宿主机端口改为
`28080`，需同时修改映射为 `setPortForwarding(28080)`，并在注册商实例上调用
`setBrowserHosts(['localhost:28080', '127.0.0.1:28080'])`。
重新生成、构建并启动容器后，服务启动脚本自动应用站点 URL 配置。

浏览器访问的是 Web 端口，Registry 的 EPP 默认端口 `700` 用于注册商协议通信，
不是网站入口。生成 Docker 配置不等于网站已启动，需等待容器初始化和 setup 完成。

## DNS 授权

Registry 在未开启 DNS 发布时可独立使用；存在 `DomainNameService` 时会先渲染该层。需要 DNS 发布授权时，在 render 前调用：

```python
dns = emu.getLayer('DomainNameService')
dns.authorizeRegistry(
    server,
    zones={
        'com': ('a-com-server', 'b-com-server'),
        'net': ('a-net-server',),
    },
)
```

`zones` 将 TLD 映射到已有 DNS 虚拟节点：第一个为主节点，第二个可选，为从节点。
每个节点必须已托管相应区域；所选节点承载的全部区域都必须列入映射。
授权区域直接与 `server.getTlds()` 校验，可以只授权其中一部分。
该方法不创建 DNS 节点、区域或根区委派；增加新 TLD 时须由入口先配置这些基础设施。
DNS 服务负责更新授权和主从配置，并调用 Registry 的 `setDnsAuthorization(tld, address, key)`
传递发布目标及同一份密钥；Registry 在安装时将发布配置写入实际绑定主机，无需重复指定 AS 和主机名。

各 TLD 使用独立的发布和区域传送 TSIG 密钥，并保护区域顶点及名称服务器记录。
只有主节点时禁止区域传送；有从节点时配置签名传送及通知。
每次 render 生成新凭据，部署时 Registry 和相关 DNS 节点应同步更新。
发布器配置写入 `/opt/registry/dns-publication-<tld>.json`，总清单为
`/opt/registry/dns-publications.json`（以 `com.` 这类区域名为键）。

授权本身不会启动发布循环。调用 Registry 实例的 `enableDnsPublication(['com', 'net'])`
可启用对应 TLD 的周期发布，默认间隔 30 秒；必须已配置这些区域的授权。

## 文件组织

Registry 使用独立模板目录和文件内容字典：

```text
DomainService/
└── RegistryService/
    ├── RegistryService.py       # Service/Server 接口与实例参数 / Interfaces and instance settings
    ├── registry_defaults.py     # 默认仿真参数 / Default simulation settings
    ├── registry_install.py      # 安装依赖、模板填充和启动顺序 / Dependencies, templates, and startup order
    └── template/
        ├── RegistryFileTemplates.py
        └── files_registry/     # 较长的 SQL、PHP、Shell 和 Nginx 配置 / SQL, PHP, shell, and Nginx templates
```

模板只描述文件结构；账号参数由 Server 传入。PHP 和 SQL 字符串分别转义，
Web 配置中的数据库密码通过带引号的 dotenv 值写入。
`DomainService` 顶层继续导出 `RegistryService`、`RegistryServer` 和 DNS 授权函数。

Registry 模板包括 `database.sql`、`database.sh`、`initialize-tlds.php`、
`configure-web.php`、`configure-component.php`、`registry.conf`、`web.sh`，
以及初始化注册商账号和预置域名的 `create-epp-registrar.php`。
简单启动命令、管理员创建短脚本、INI、cron 和 EPP/DAS 配置片段直接写在
`registry_install.py` 中；容器内生成的配置文件与启动顺序保持不变。

## FOSSBilling 注册商服务

服务按 Registry 的组织方式拆分为 `FossBillingService.py`、默认参数、安装函数和
`template/files_fossbilling/` 模板；固定 FOSSBilling 0.8.7 和 EPP 安装器版本。

```python
from DomainService import FossBillingService

registrar_service = FossBillingService()
registrar = registrar_service.install('fossbilling')
registrar.setRegistry('registry')
registrar.setTlds(['com', 'net'])
registrar.setTldPrice('com', registration='11.99', renewal='11.99', transfer='11.99')
registrar.setAdminAccount('admin@example.com', 'Aa123456')
registrar.setClientAccount('user@example.com', 'Aa123456')
registrar.setReservedDomains(['google.com', 'twitter.com', 'example.com'])
registrar.setBrowserHosts(['localhost:18080', '127.0.0.1:18080'])
emu.addLayer(registrar_service)
emu.addBinding(Binding('fossbilling', filter=Filter(asn=150, nodeName='host_1')))
registrar.setPortForwarding(18080)
```

`setRegistry()` 接受 Registry 虚拟节点名及可选 `username`、`password`、`prefix`。
渲染时从绑定主机读取地址，从 Registry 实例读取 EPP 端口，生成连接参数和来源 IP 白名单。
Registry 与 FOSSBilling 必须使用不同主机。多个注册商需使用不同账号和前缀。
省略 `setTlds()` 时继承 Registry 的 TLD；显式设置时必须是其子集。
默认首次售价为 11.99，初始化脚本保留已有 TLD 的价格，不删除已有商品。
`setClientAccount(..., profile={...})` 可覆盖默认联系资料；可用字段见 `fossbilling_defaults.py`。
`setBrowserHosts()` 只控制允许的浏览器来源，不添加端口映射；空列表禁用来源覆盖。

Registry 在数据库初始化后、EPP 启动前创建账号、白名单和指定的预置域名，
注册商连接该 Registry 实例的 EPP 进程，无需手动创建第二个 EPP 服务。
已有 EPP 账号密码或前缀不同会拒绝覆盖，预置域名属于其他注册商时也会报错。
这不是运行中账号的密码轮换接口，改变绑定 IP 后需重新生成并部署。
EPP 使用仿真自签名证书及对应的适配器验证配置。

FOSSBilling 的应用安装由服务生成的 `initialize-fossbilling.py` 在容器启动时自动执行：
等待本机数据库和 Web，从 `setup-config.json` 和 `epp-connection.json` 读取配置，
完成首次安装、URL 配置、TLD 绑定、客户创建、安装器移除和 cron 配置。
成功后写入 `/run/fossbilling-initialized`，失败写入 `/run/fossbilling-initialization.failed`，
日志位于 `/var/log/fossbilling-initialize.log`。`setup_fossbilling.py` 只等待初始化结果并验证 EPP 和客户登录。
已有管理员保留；已有演示客户需密码匹配，仅补齐缺失联系资料。已有商品价格保留。
结账逻辑在事务提交后再开通订单。

初始化参数含仿真凭据，生成文件限制为 root 可读；构建目录和模拟器快照也包含这些参数。
具体运行命令见 [H10 示例](../../examples/H10_domain_name_purchase/README.md)。

## 重建与初始化示例

在 `examples/H10_domain_name_purchase` 目录，使用已安装 SeedEmu 依赖的虚拟环境依次运行：

```bash
python domain_name_purchase.py
cd output
docker compose build
docker compose up -d
cd ..
python setup.py
```

`domain_name_purchase.py` 固定构建 Registry、FOSSBilling、DNS Hosting 和 FakePayment，只生成部署文件，需进入 `output` 手动执行 `docker compose build` 和 `docker compose up -d`；各服务在启动时完成本地初始化，`setup.py` 负责跨容器配置及验证。
`setup.py` 等待自动初始化后执行验证。跨容器配置失败可重跑 setup；本地初始化失败需先查看日志、修复并重启对应容器。
Python 入口不调用 Docker 构建或启动命令。
详见 [启动说明](../../examples/H10_domain_name_purchase/README.md)。

## DNS Hosting 与 Registry 委派发布

`DnsHostingService` 集成固定版本 BIND API 和 FOSSBilling DNS Hosting 扩展。示例入口为
[`domain_name_purchase.py`](../../examples/H10_domain_name_purchase/domain_name_purchase.py)。

在 `examples/H10_domain_name_purchase` 下运行：

```bash
python domain_name_purchase.py
cd output
docker compose build
docker compose up -d
cd ..
python setup.py
```

此场景沿用 `.com/.net` 的 Registry 和 FOSSBilling，增加 AS170 的两个已有主机：
`host_0` 为主 DNS，`host_1` 为从 DNS；托管 API 与主 DNS 共用 `host_0`。网站入口保持上述 18080/18081 映射，
DNS Hosting 在 FOSSBilling 普通用户入口内购买和管理，没有独立的 18082 管理网页。
BIND API 仅监听各节点内部 IPv4 的 7650 端口，不添加宿主机端口映射。

### 入口配置

在同一个 `DomainNameService` 中依次安装主、从 DNS，并绑定到不同的已有 Host：

```python
from DomainService import DnsHostingService

# 主节点先安装，确保 ns1/ns2 与主从地址一致。
# Install the primary first so ns1/ns2 match primary/secondary addresses.
dns.install('hosted-dns-primary').addZone('example.com.').setMaster()
dns.install('hosted-dns-secondary').addZone('example.com.')
emu.addBinding(Binding('hosted-dns-primary', filter=Filter(asn=170, nodeName='host_0')))
emu.addBinding(Binding('hosted-dns-secondary', filter=Filter(asn=170, nodeName='host_1')))

dns_hosting_service = DnsHostingService()
hosting = dns_hosting_service.install('dns-hosting')
hosting.setNameServers('hosted-dns-primary', 'hosted-dns-secondary', domain='example.com')
hosting.setRegistrar('fossbilling')
emu.addLayer(dns_hosting_service)
# 托管 API 与主 DNS 共用主机，需要允许绑定已使用的节点。
# The hosting API shares the primary DNS host, so allow binding to an already-bound node.
emu.addBinding(Binding('dns-hosting', filter=Filter(asn=170, nodeName='host_0', allowBound=True)))
```

每对 DNS 节点仅托管所选静态服务域名，不能使用其他自定义 include；由 BIND API 创建的客户区域另行管理。
主从地址、注册商来源 IP 和产品 NS 配置从绑定节点解析，不固定为 `10.170.0.71/72`。
当前每个 FOSSBilling 实例只配置一对托管 DNS，各实例不能共用同一对节点。
`domain` 支持二级 ASCII 域名，需要先在 FOSSBilling 实例的 `setReservedDomains()` 中预留。
示例在 FOSSBilling 配置部分统一预留 `google.com`、`twitter.com`、`example.com`。

Registry 实例使用：

```python
registry_server.enableDnsPublication(['com', 'net'], interval=30)
```

只允许发布 Registry 管理且已授权的 TLD。发布器读取现有 EPP 数据库配置和每个 TLD 的
`dns-publication-<tld>.json`，用 TSIG 向对应父区提交 NS/glue 更新。
每个 TLD 使用独立状态文件和进程锁；更新失败不保存成功状态，后续循环会重试。
未登记 NS、处于 clientHold/serverHold 或不满足有效期条件的域名不会被发布。
发布器只处理 NS 和域内 glue，不创建客户的 A/AAAA 网站记录。

### 初始化与数据边界

`setup.py` 按以下顺序执行：

1. 等待 Registry 和 FOSSBilling 自动初始化，验证 EPP 与客户登录。
2. 等待 Registry 启动脚本完成 NS 登记，以只读方式核对 `ns1.example.com`、`ns2.example.com` 的 host、IPv4 和状态。
3. 读取主从容器启动时生成的 API 凭据，检查端口并使用插件客户端验证认证。
4. 激活 DNS 扩展并配置 Bind 产品及商品分类。

已有 Registry host 会核对归属、父域、地址和状态，冲突时回滚而不覆盖。
host 登记不等于为域名设置 NS 委派，也不修改静态区的网站记录。
已有 DNS 产品保留价格；无产品时创建免费仿真产品；多个产品时使用
`python setup.py --dns-product-id ID` 指定目标。
凭据不写入命令行或日志，初始化不会自动开通或重试已有客户订单，也不重试付款。

购买并配置域名时，需分别完成域名 NS 设置、DNS Hosting 服务开通和网站记录配置。
验收也应分别检查 Registry 域名/NS、父区委派、主从权威区及递归解析。
静态服务域名、商品配置成功或 API 登录成功都不等于客户域名已可解析。


## FakePayment 模拟支付

`FakePaymentService` 为域名购买环境增加独立收银台及
FOSSBilling 支付适配器，仅用于仿真，不涉及真实资金。入口与其他场景放在同一目录：
`examples/H10_domain_name_purchase/domain_name_purchase.py`。

在 `examples/H10_domain_name_purchase` 下使用已配置的虚拟环境执行：

```bash
python domain_name_purchase.py
cd output
docker compose build
docker compose up -d
cd ..
python setup.py
```

仍使用默认 `output`，进入该目录手动执行 `docker compose build` 和 `docker compose up -d`；setup 依次完成
Registry/FOSSBilling 就绪与登录验证、DNS Hosting 商品配置、FakePayment 运行验证。
默认支付容器对应 Compose 服务 `hnode_160_host_1`，可用 `--payment-service` 覆盖。
仅验证网关时可直接调用 `FakePaymentService/setup_fake_payment.py`，传入
`--container <FOSSBilling容器>` 和 `--payment-container <收银台容器>`。
脚本先核对双方配置及签名密钥，再从注册商探测收银台；不会创建发票或自动支付订单。

| 服务 | 宿主机访问地址 | 用法 |
| --- | --- | --- |
| FOSSBilling 普通入口 | `http://localhost:18080/` | 登录客户账号，购买服务并打开发票 |
| FOSSBilling 管理员入口 | `http://localhost:18080/admin` | 管理商品、发票及网关 |
| Registry 管理面板 | `http://localhost:18081/` | 管理注册局数据 |
| FakePayment 健康检查 | `http://localhost:18083/health` | 就绪时返回 `ok` |
| FakePayment 收银台 | `http://localhost:18083/pay` | 从发票选择 fakePayment 后提交签名表单进入 |

收银台的 `/pay` 只接受 POST，直接在地址栏访问会返回 404；DNS Hosting 在普通用户入口内管理。
确认模拟付款后，需分别检查发票付款状态、订单激活状态、Registry 注册结果与 DNS 发布，
收银台显示“已提交”或 setup 成功不代表这些业务步骤全部完成。

### 自定义绑定与端口

```python
from DomainService import FakePaymentService

fake_payment_service = FakePaymentService()
checkout = fake_payment_service.install('fake-payment')
checkout.setRegistrar('fossbilling').setPort(8080)
checkout.setBrowserUrls({'localhost:18080': 'http://localhost:18083/pay',
                         '127.0.0.1:18080': 'http://127.0.0.1:18083/pay'})
emu.addLayer(fake_payment_service)
emu.addBinding(Binding('fake-payment', filter=Filter(asn=160, nodeName='host_1')))
checkout.setPortForwarding(18083)
```

内部支付地址与注册商回调地址从绑定节点解析，不固定拓扑 IP。每个注册商只能关联一个
FakePayment 实例，收银台与注册商必须使用不同主机。
网关由注册商容器内的 `setup-gateway.sh` 在本地 FOSSBilling 初始化成功后启用，
日志位于 `/var/log/fake-payment-initialize.log`；宿主机 setup 只验证网关，不再修改其数据库记录。
`setPort()` 设置容器端口，`setPortForwarding()` 设置宿主机映射，`setBrowserUrls()` 将
FOSSBilling 浏览器 Host 映射为浏览器可访问的收银台 URL。修改宿主机端口时需同步修改后两项；
修改注册商入口还需同步其 `setBrowserHosts()`。未匹配的 Host 使用仿真网络支付地址。
调用 `setBrowserUrls({})` 可仅使用内部地址。

`setSharedSecret()` 可替换默认演示签名密钥，服务会将同一值写入双方容器；密钥不应提交到仓库。
此默认密钥仅适用于仿真。变更地址、端口或密钥后需重新生成并重建容器。


setup 会先检查完整环境的组件配置；已部署容器缺少 DNS Hosting 或支付组件时会明确报错，需先重建完整场景，再运行 setup。仅运行 setup 无法安装镜像中缺少的组件。

清理当前示例容器、网络和数据卷时，在 `examples/H10_domain_name_purchase` 下执行：

```bash
docker compose -f output/docker-compose.yml down --remove-orphans --volumes
```

上述命令清理同一 Compose 项目的容器、网络和项目管理的数据卷，包括旧部署遗留的容器。
使用自定义输出目录时，将 `output/docker-compose.yml` 替换为对应路径。
容器可写层及项目数据卷会被删除，镜像、生成文件、外部数据卷和宿主机绑定挂载目录会保留。
清理命令不会自动执行构建或初始化。

## H11：浏览器与 Agent 同容器

[H11 使用说明](../../examples/H11_browser_agent/README.md) 提供完整域名服务加 browser-agent 的独立示例。
通过 `Docker.attachCustomContainer()` 接入 AS154/net0，而非占用原有 Host。
Agent 网页映射到 `http://localhost:18089/`，agent 和 Chromium 均安装在该容器镜像中。
出网地址填写在 H11 的 `egress_urls.txt`，每行一个 URL、域名或 IP；启动时自动配置 DNS 和路由。
修改地址后重启 browser-agent 即可，无需修改网络脚本或重建镜像（首次应用此功能需重新生成配置并手动构建启动容器）。
在 H11 目录运行 `python browser_agent.py`，进入 `output` 执行 `docker compose build`、`docker compose up -d`，返回 H11 后运行 `python setup.py`。
清理使用 `docker compose -f output/docker-compose.yml down --remove-orphans --volumes`，自定义输出目录需替换配置路径。
H10 和 H11 默认使用同一 Compose 项目和业务端口，应作为替代场景运行。

## 构建缓存与安装失败

依赖安装使用 Docker BuildKit 缓存。Registry、FOSSBilling 和 DNS 托管的基础包、
PHP 软件源、系统服务、PHP 扩展、源码下载及 Composer 安装分层执行。
每个 apt 安装层先更新软件索引，再安装该层需要的包，避免复用过期索引安装新增包。

apt 下载保存在共享的 `/var/cache/apt` 构建缓存中；Composer 下载使用
`/var/cache/composer`。缓存加锁，多个服务同时构建时会等待锁，避免并发修改缓存。
apt 下载启用最多三次重试和连接超时；软件源配置及 Composer 安装最多尝试三次，
最终失败仍返回非零退出码。输出保留工具原始日志。

H11 另外缓存 pip 下载，将系统依赖、桌面组件、Python 包、Chromium 系统依赖及
浏览器安装拆开。agent 源码和模型配置在这些依赖层之后复制，修改源码不会主动重装依赖。

首次应用新的 Dockerfile 会重建受影响层；之后指令和基础镜像未变时复用成功层。
即使安装层失败，下载缓存仍可供重跑使用，但无法消除持续的代理或软件源故障。
上述 Compose 清理命令不清理镜像或 BuildKit 缓存；手动清除构建缓存后需要重新下载。
镜像基础软件层由编译器生成，其缓存行为仍由 Docker 管理。
