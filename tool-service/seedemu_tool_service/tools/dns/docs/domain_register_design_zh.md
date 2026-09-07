# source 自有 DNS 与域名注册设计

## 设计概览

B02a 展示 Agent 如何在 SeedEmu 网络内配置自有权威 DNS，并通过 Loom 和 Namingo 注册 `example.com`。系统由四个部分组成：Agent 工具层、Registrar 侧、Registry 侧，以及父区和子区 DNS。

```mermaid
%%{init: {"theme": "base", "flowchart": {"rankSpacing": 70, "nodeSpacing": 30}, "themeVariables": {"background": "#000000", "primaryColor": "#111827", "primaryTextColor": "#ffffff", "primaryBorderColor": "#9ca3af", "lineColor": "#d1d5db", "clusterBkg": "#0b0f14", "clusterBorder": "#6b7280", "edgeLabelBackground": "#000000"}}}%%
flowchart TD
    agent["Agent"]

    subgraph tool_layer["Agent 工具层"]
        tools["DNS / domain tools"]
        runtime["Docker RuntimeBackend"]
        source["所选 source<br/>网络请求与本地 session"]
    end

    subgraph registrar_side["Registrar 侧"]
        loom["Loom HTTPS 前端<br/>客户、订单、账单、域名生命周期"]
        loom_db[("Loom MariaDB")]
        loom_epp["Loom Namingo EPP client"]
        namingo["Namingo Registrar<br/>loom backend"]
        rdds["WHOIS / RDAP"]
    end

    subgraph registry_side["Registry 侧"]
        registry["Namingo Registry<br/>EPP 与注册对象"]
        registry_db[("Registry MariaDB")]
        writer["Registry Zone Writer"]
    end

    subgraph parent_dns[".com 父区权威 DNS"]
        hidden["隐藏 Primary"]
        public_b["公共 Secondary B"]
        public_c["公共 Secondary C"]
    end

    subgraph child_dns["source 自有 example.com DNS"]
        child_primary["ns1 Primary"]
        child_secondary["ns2 Secondary"]
    end

    agent -->|"调用工具"| tools --> runtime --> source
    source -->|"HTTPS 表单与 session"| loom
    loom --> loom_db
    loom -->|"已支付订单"| loom_epp -->|"EPP over mutual TLS"| registry
    namingo -->|"loom adapter 只读查询"| loom_db
    namingo --> rdds
    registry --> registry_db --> writer
    writer -->|"发布 .com zone"| hidden
    hidden -->|"NOTIFY + AXFR/IXFR"| public_b
    hidden -->|"NOTIFY + AXFR/IXFR"| public_c
    source -->|"dns.configure"| child_primary
    child_primary -->|"AXFR/IXFR"| child_secondary
    classDef dark fill:#111827,stroke:#9ca3af,color:#ffffff
    class agent,tools,runtime,source,loom,loom_db,loom_epp,namingo,rdds,registry,registry_db,writer,hidden,public_b,public_c,child_primary,child_secondary dark
    style tool_layer fill:#151008,stroke:#f59e0b,color:#ffffff
    style registrar_side fill:#0b1220,stroke:#60a5fa,color:#ffffff
    style registry_side fill:#17110a,stroke:#f59e0b,color:#ffffff
    style parent_dns fill:#1a0d14,stroke:#f472b6,color:#ffffff
    style child_dns fill:#071a12,stroke:#4ade80,color:#ffffff
```

Loom 是购买流程的业务入口。它保存客户、订单和账单，在付款成功后通过 EPP 向 Namingo Registry 创建 contact、host 和 domain 对象。Namingo Registrar 使用 `loom` backend 读取同一份 Loom 数据，为注册结果提供 WHOIS 和 RDAP 查询。Registry 的 Zone Writer 再把有效委派发布到 `.com` 权威 DNS。

父区和子区分别管理不同的数据：`.com` 保存 `example.com` 的 NS 与 glue；source 自有 DNS 保存 `www.example.com` 等域内记录。两者通过正常 DNS 委派连接。

## Agent 工具调用流程

```mermaid
sequenceDiagram
    participant A as Agent
    participant T as tool-service
    participant S as selected source
    participant L as Loom
    participant R as Namingo Registry
    participant P as .com DNS
    participant D as example.com DNS

    A->>T: domain.registrar_find
    T-->>A: Loom origin
    A->>T: dns.configure(zone, A record)
    T->>S: 执行 DNS 配置
    S->>D: 更新 Primary 并同步 Secondary
    D-->>A: 权威响应与 SOA 收敛
    A->>T: domain.registrar_request(GET /)
    T->>S: 建立 source-local session
    S->>L: HTTPS + source token
    L-->>A: HTML、session_id、CSRF 表单
    A->>T: domain.registrar_request(注册表单)
    T->>L: 域名、联系人、NS 与 glue
    L-->>A: invoice 跳转
    A->>T: domain.registrar_request(支付表单)
    T->>L: 余额付款
    L->>R: EPP contact/host/domain create
    R-->>L: 注册成功
    R->>P: Zone Writer 发布 NS/glue
    A->>T: dns.check_delegation
    T->>P: 查询父区 referral/glue
    T->>D: 查询子区 NS/SOA
    A->>T: dns.lookup（两台递归解析器）
    T-->>A: www.example.com A
```

实际调用步骤如下：

1. Agent 调用 `domain.registrar_find`，从显式发布的 metadata 中发现 Loom origin。
2. Agent 调用 `dns.configure`，先创建 `example.com` 子区并写入 `www` 等记录；工具同时验证 Primary、Secondary 和 SOA。
3. Agent 调用 `domain.registrar_request` 请求 Loom 首页。工具从所选 source 建立认证 session，并返回页面、`session_id` 和 HTTP 证据。
4. Agent继续用同一 `session_id` 读取注册表单，保留 CSRF 字段，再提交域名、联系人、`ns1/ns2` 和 glue 地址。
5. Loom 创建订单和账单；Agent读取支付页面并提交余额付款。
6. Loom 的 EPP client 向 Namingo Registry 创建注册对象。Registry 成功提交后，Zone Writer 发布 `.com` 委派。
7. Agent 调用 `dns.check_delegation`，确认父区 NS/glue 与两台子区权威服务器一致。
8. Agent 调用 `dns.lookup`，分别通过 B02a 的两台递归解析器验证最终 A 记录。

Registrar session 和私有凭据保留在所选 source 内；Agent 通过工具看到的是可发现的 Loom 页面和结构化 DNS 结果。父区变更经 Registrar/Registry 完成，而购买后的普通子区记录继续使用 `dns.configure` 更新。

## Namingo Registrar 与 Loom

B02a 将 `NamingoRegistrarService` 配置为 `loom` backend。Namingo Registrar 通过专用只读账号连接 Loom MariaDB，因此 WHOIS/RDAP 与 Loom 订单展示的是同一份 Registrar 数据。B02a 不启用 Namingo automation，订单驱动的域名生命周期由 Loom 负责。

## DNS 发布与解析

Namingo Registry 将注册数据交给 Zone Writer，Zone Writer 发布到 `.com` 隐藏 Primary，再通过 NOTIFY 和 TSIG 保护的 AXFR/IXFR 同步两台公共 Secondary。递归解析器从公共 Secondary 获得 `example.com` 的 referral 和 glue，随后查询 source 自有权威 DNS。

动态委派可能受到递归缓存影响，因此完整测试分别等待两台递归解析器收敛，而不是只验证其中一台，也不会通过清空缓存伪造成功。

## 实现与验证

主要实现位于：

- `seed-emulator/examples/internet/B02a_domain_registration/domain_registration.py`
- `seed-emulator/seedemu/services/LoomRegistrarService.py`
- `seed-emulator/seedemu/services/NamingoRegistrarService.py`
- `seed-emulator/seedemu/services/NamingoRegistryService.py`
- `seedemu-agent-tools/tool-service/seedemu_tool_service/tools/dns/`

Docker 购买测试覆盖 Loom session、下单付款、EPP 注册、WHOIS/RDAP、父区委派、子区权威响应，以及两台递归解析器的最终解析。
