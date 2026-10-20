# H10：域名购买与 DNS 托管

本示例提供 Registry、FOSSBilling、主从 DNS Hosting 和 FakePayment，完成域名购买、
模拟付款和 DNS 配置所需的服务部署。场景入口负责主机绑定、端口、账号、TLD 和商品参数；
服务包负责生成安装和启动操作。

## 目录

```text
H10_domain_name_purchase/
├── domain_name_purchase.py
├── setup.py
└── output/
```

## 启动与初始化

准备能够导入 `seedemu` 和 `DomainService` 的 Python 环境，以及可用的 Docker Compose。
在本示例目录执行：

```bash
python domain_name_purchase.py
cd output
docker compose build
docker compose up -d
cd ..
python setup.py
```

构建入口固定包含全部四项服务。
`domain_name_purchase.py` 只生成 `output` 中的部署文件；进入该目录后手动构建和启动容器。
已有镜像层可以命中构建缓存；构建未命中缓存时需要联网下载依赖。
容器启动时，服务自动完成本地初始化：

- FOSSBilling：等待本机数据库和 Web，首次安装，配置站点 URL、EPP/TLD、演示客户及 cron，并移除安装器。
- Registry：在注册商及预留域名创建后登记托管 NS host；已有记录仅核对，不覆盖。
- FakePayment：在 FOSSBilling 初始化成功后启用本地支付网关。

`setup.py` 保留启动后的操作：

1. 检查完整环境的组件并等待 Registry、FOSSBilling 初始化完成。
2. 验证 EPP 登录及客户登录。
3. 等待并核对托管 NS host，读取主从 BIND API 动态凭据，验证连接并配置 DNS Hosting 商品。
4. 核对支付双方配置、签名密钥、收银台连接及已启用网关，不再写入网关配置。

步骤失败会停止后续操作并返回非零退出码。setup 不构建或启动容器，也不再负责本地数据库初始化。
服务初始化失败时先检查对应容器日志：
`/var/log/fossbilling-initialize.log`、`/var/log/registry-hosts-example.com.log`、
`/var/log/fake-payment-initialize.log`。修复后重启对应容器以重跑本地初始化，再运行 setup。
已有管理员、客户和商品价格会保留；客户密码或 NS 归属不匹配时会报错，不覆盖原数据。
跨容器验证或 DNS 商品配置失败时可单独重跑 `python setup.py`。这些流程不会自动支付发票或重试客户订单。

## 生成参数

Python 入口只生成配置，不执行 Docker 构建或启动。

构建入口和 setup 均支持 `--output 路径`，应使用相同目录。
构建入口支持 `--platform amd` 或 `--platform arm`；setup 的 `--timeout` 控制 Registry 等待时间，默认 240 秒。

## 网站入口

完成启动和初始化后，在宿主机浏览器访问：

| 入口 | 地址 |
| --- | --- |
| FOSSBilling 普通用户 | <http://localhost:18080/> |
| FOSSBilling 管理员 | <http://localhost:18080/admin> |
| Registry 管理面板 | <http://localhost:18081/> |
| FakePayment 健康检查 | <http://localhost:18083/health> |

FOSSBilling 示例管理员为 `admin@example.com`，客户为 `user@example.com`，密码均为 `Aa123456`。
Registry 示例管理员为 `admin@example.com`，密码为 `123456`。首次初始化参数可在场景入口修改。

模拟付款从 FOSSBilling 发票选择 fakePayment 进入；收银台 `/pay` 只接受签名 POST，
直接在地址栏打开会返回 404。DNS Hosting 在普通用户入口购买和管理，没有独立管理网站。
浏览器与 agent 聊天界面由 [H11 示例](../H11_browser_agent/README.md) 提供。

端口映射使用服务实例的 `setPortForwarding(host_port)`，传入 `None` 可禁用。修改 FOSSBilling 端口还需同步 `setBrowserHosts()`；
修改支付入口还需同步 `setBrowserUrls()`。详细配置见 [服务说明](../../services/DomainService/README.md)。

## DNS 托管和解析

默认销售 `.com`、`.net`；完整场景预留 `google.com`、`twitter.com`、`example.com`。
托管名称服务器为 `ns1.example.com`、`ns2.example.com`，地址分别为 `10.170.0.71`、`10.170.0.72`。
主从 BIND API 监听内部 7650 端口，不映射宿主机端口。

客户域名需要分别完成注册、NS 设置、DNS Hosting 开通及 A/AAAA 等记录配置。
Registry 发布器把 NS/glue 更新到父区，每轮完成后等待 30 秒；递归缓存可能继续保留旧结果。
可分别查询权威 DNS 和递归 DNS，以区分记录配置与委派、缓存问题：

```bash
dig @10.170.0.71 www.your-domain.com A +norecurse
dig @10.153.0.53 www.your-domain.com A
```

以上命令在能访问仿真网络的容器中执行，请替换为实际域名。
setup 成功不等于购买或解析成功，需分别核对发票、订单、Registry 注册、父区委派和权威记录。

## 容器定位与商品选择

setup 使用以下固定 Compose 服务名定位容器，可通过参数覆盖：

| 服务 | Compose 服务名 | 自定义参数 |
| --- | --- | --- |
| Registry | `hnode_151_host_1` | `--registry-service` |
| FOSSBilling | `hnode_150_host_1` | `--fossbilling-service` |
| 主 DNS | `hnode_170_host_0` | `--primary-dns-service` |
| 从 DNS | `hnode_170_host_1` | `--secondary-dns-service` |
| 收银台 | `hnode_160_host_1` | `--payment-service` |

修改绑定节点后需同步指定服务名。存在多个 DNS 商品时使用 `--dns-product-id ID` 选择目标。
已有商品保留价格，无商品时创建免费仿真托管商品。

## 清理与数据

```bash
docker compose -f output/docker-compose.yml down --remove-orphans --volumes
```

上述命令删除同一项目的容器、
网络和项目管理的数据卷，包括遗留容器；保留镜像、构建缓存和生成文件。
使用自定义输出目录时，将命令中的 `output/docker-compose.yml` 替换为对应路径。
外部卷及宿主机绑定挂载目录不会删除。容器未持久化的数据会随容器删除而丢失。

H10 和 H11 默认都使用 Compose 项目 `output`，业务端口也相同，应选择一个部署。
构建入口不会自动清理数据；切换部署前请确认需要保留的数据。脚本仅透传底层命令输出及必要错误信息。
