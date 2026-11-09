#!/usr/bin/env python3
"""Build the Mastodon social media and domain purchase environment for E15."""

import argparse
from ipaddress import ip_address
import re
import shutil
from urllib.parse import urlsplit
from pathlib import Path
import sys
import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT.parent / 'seed-emulator'))
sys.path.insert(0, str(ROOT / 'services'))
sys.path.insert(0, str(ROOT))

from examples.H00_mini_internet import build_emulator as build_mini_internet
from DomainService import (
    DnsService, DnsServiceMerger, DomainDataService,
    NamingoRegistryService, FossBillingRegistrarService, FakePaymentService,
)
from seedemu.compiler import Docker, Platform
from seedemu.core import Action, Binding, Emulator, Filter
from services.SocialMediaService import SocialMediaService
from seedemu.services import CAService, RootCAStore
from services.AgentService import AgentService, ToolPackage
from services.AgentService.runtime.emuvista_agent.launch import read_environment
from seedemu.layers import PeerRelationship


def configure_agents(emu, env_file):
    """Run Alice and Bob with E99's framework and E15's service tools."""
    agents = AgentService().addNetworkTools()
    agents.addToolPackage(ToolPackage('world', ROOT / 'examples/H99_virtual_world/tools/world'))
    agents.addToolPackage(ToolPackage('socialmedia', ROOT / 'services/AgentService/tools/socialmedia',
                                      requirements=('pydantic>=2,<3',)))
    agents.addToolPackage(ToolPackage('dns', ROOT / 'services/AgentService/tools/dns',
                                      software=['dnsutils']))
    agents.addToolPackage(ToolPackage('domain_purchase', ROOT / 'services/AgentService/tools/domain_purchase'))
    clients = yaml.safe_load((HERE / 'domains.example.yaml').read_text())['clients']
    directory = {'services': {
        'mastodon': {'url': 'https://mastodon.com:18443/api/v2/instance'},
        'registrar': {'url': 'http://fossbilling.com:8080/'},
        'registry': {'url': 'http://registry.com:8080/'},
        'payment': {'url': 'http://10.160.0.71:8080/health'},
    }}
    tools = [
        'network.identity', 'network.resolve', 'world.catalog', 'world.probe',
        'socialmedia.timeline_read', 'socialmedia.account_lookup',
        'socialmedia.account_statuses', 'socialmedia.status_context', 'socialmedia.status_create',
        'dns.lookup', 'domain_purchase.purchase', 'domain_purchase.status',
        'domain_purchase.set_nameservers', 'domain_purchase.hosting_purchase',
        'domain_purchase.hosting_status',
    ]
    for index, name in enumerate(('alice', 'bob')):
        node = emu.getLayer('Base').getAutonomousSystem(161).createHost('agent_' + name)
        node.joinNetwork('net0', address=f'10.161.0.{80 + index}')
        agent_tools = tools if name == 'alice' else [tool for tool in tools if not tool.startswith('domain_purchase.')]
        agent = agents.install(name).allowTools(*agent_tools)
        agent.setFramework(ROOT / 'experiments/E99_virtual_world/adapters/langchain',
                           requirements=['langchain==1.4.9', 'langchain-openai==1.7.4'])
        if env_file is not None:
            agent.setEnvironmentFile(env_file)
        agent.setService('world', directory)
        if name == 'alice':
            customer = clients['client-alice']
            agent.setService('domain_purchase', {
                'registrar_url': 'http://10.150.0.71:8080',
                'payment_url': 'http://10.160.0.71:8080',
                'email': customer['email'], 'password': customer['password'],
                'currency': 'USD', 'tlds': ['com', 'net'],
                'state_dir': '/home/emuvista-agent/domain-purchases',
            })
            node.addPersistentStorage('/home/emuvista-agent/domain-purchases',
                                      name='e15-domain-purchases-' + name)
            node.addBuildCommandAtEnd('install -d -o 10001 -g 10001 -m 700 /home/emuvista-agent/domain-purchases')
        else:
            agent.setService('fossbilling_admin', {
                'registrar_url': 'http://10.150.0.71:8080',
                'email': 'admin@example.com', 'password': 'Aa123456',
            })
        node.addPersistentStorage('/run/socialmedia', name='e15-socialmedia-' + name, read_only=True)
        agent.setService('socialmedia', {
            'instance_url': 'https://mastodon.com:18443',
            'credential_file': '/run/socialmedia/credentials.json',
        })
        if name == 'bob':
            role = '你是 Bob，FOSSBilling 的域名销售员工。'
            business_info = (
                '你被分配了 FOSSBilling 管理员账号，凭据保存在 fossbilling_admin 服务配置中；不要公开凭据。'
                '当前尚无管理员查询工具，不要声称已登录后台或查看实时数据。'
                '业务参考：注册商入口 http://fossbilling.com:8080/；.com、.net 初始化注册价均为 11.99 USD/年。'
                'DNS Hosting 默认免费，是解析托管而非网站空间；NS 为 ns1.example.com 和 ns2.example.com。'
                '上述为初始化配置，已有数据可能保留旧价格，实际费用以注册商账单为准。'
                '域名注册、修改 NS、开通 DNS Hosting 和添加解析记录是不同操作。'
                'NS 必须使用上述 ns1.example.com、ns2.example.com，不猜测其他服务器名称、后台菜单或优惠。'
            )
            task = (
                '在 Mastodon 寻找 Alice 关于建立网站的求助帖，在该帖下回复，帮助她理解并完成建站所需的准备。'
                '先回答她的问题，再介绍一个相关的下一步；说明域名、DNS 解析托管与网站空间的区别。'
                '围绕她的建站需求介绍 FOSSBilling 的域名及 DNS Hosting 服务，引导她自行决定是否购买和配置。'
                '不要另发广告或转去闲聊；她已经回答时继续提供帮助，不要等待她主动问出每一步。'
                '尚未找到求助帖时浏览最新帖子；没有实际完成的操作不要声称已经完成。'
            )
            task += business_info
        else:
            role = '你是 Alice，一位想建立个人网站、正在 Mastodon 寻求教程和帮助的初学者。'
            task = (
                '先查看自己是否已有建站求助帖；没有时发布一条公开求助，说明想建立个人网站，希望获得适合初学者的教程。'
                '已有求助帖就持续查看该帖的回复，在同一对话中回答对方的问题，追问不理解的步骤。'
                '交流围绕如何建站、选择域名、配置解析及网站部署展开，不发布无关生活帖，也不重复发起求助。'
                '根据得到的信息自行选择下一步；需要购买域名或 DNS Hosting 时可以使用自己的工具，并核实实际结果。'
                '域名购买或 DNS Hosting 开通不等于网站已经部署，不要把尚未完成的步骤报告为成功。'
            )
        task += (
            '每轮先实际读取最新信息。首次通过账号帖子或 public 时间线找到求助帖，之后用该原帖的真实 ID 调用 socialmedia.status_context，'
            '检查 descendants 中尚未回应的消息；原帖发布时间不会因回复而更新，不能只看最新时间线判断有没有回复。'
            'status_context 不传 limit；查询失败不等于没有回复。'
            '先回应对方未回答的问题；对方已回答时继续相关解释或追问。只有自己明确提出的问题尚未得到回答时才等待。'
            '回复时使用 in_reply_to_id 指向所回应的消息并提及对方，所有交流保持在同一求助线程内。'
            '每轮最多发一条，不重复发送相同内容或催促；无新内容可不发帖，发送结果不确定时先核实。'
            '发帖用简短纯文本，最多 500 字符；一次只讲当前最相关的一步，不发送长教程或 HTML。'
            '只有发帖结果 successful=true 且有 status.id 才算送达并等待回复；明确拒绝时按错误缩短或修正内容，'
            '修改内容后使用新的 idempotency_key；outcome_unknown=true 时先核实，不能盲目重发。'
        )
        agent.setService('persona', {
            'system': role,
            'task': task, 'requiredServices': ['mastodon'],
        })
        emu.addBinding(Binding(name, filter=Filter(asn=161, nodeName='^agent_' + name + '$')))
    emu.addLayer(agents)


def add_model_egress(emu, base_url):
    """Use E99's native real-world routing and forward only the LLM hostname."""
    parsed = urlsplit(base_url)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname:
        raise ValueError('LLM_BASE_URL must be an HTTP(S) endpoint')
    outside = emu.getLayer('Base').createAutonomousSystem(99999)
    outside.createRealWorldRouter('llm-egress', prefixes=['0.0.0.0/1', '128.0.0.0/1']).joinNetwork('ix100', '10.100.0.99')
    emu.getLayer('Ebgp').addPrivatePeerings(100, [3], [99999], PeerRelationship.Provider)
    host = parsed.hostname
    try:
        ip_address(host)
        return None
    except ValueError:
        pass
    if not re.fullmatch(r'[A-Za-z0-9.-]+', host):
        raise ValueError('invalid LLM hostname')

    def forward():
        resolver = emu.getBindingFor('dns-resolver')
        resolver.appendFile('/etc/bind/named.conf.local',
                            f'\nzone "{host}" {{ type forward; forward only; forwarders {{ 1.1.1.1; 8.8.8.8; }}; }};\n')
    return forward


def build_emulator(*, env_file=None):
    """Build E15 services directly on the shared H00 topology."""
    emu = build_mini_internet()
    # Use the native merge API to install the DNS subclass, retaining H00 zones, nodes and bindings.
    dns_extension = Emulator()
    dns_extension.addLayer(DnsService())
    emu = emu.merge(dns_extension, [DnsServiceMerger()])
    # ------------------------------------------------------------------------
    # Registry and DNS publication authorization
    # ------------------------------------------------------------------------
    registry_service = NamingoRegistryService()
    registry_server = registry_service.install('registry')
    registry_server.setPortForwarding(18081)
    registry_server.setTlds(['com', 'net'])
    registry_server.setAdminAccount('admin@example.com', '123456')
    registry_server.setDatabasePassword('registry-database-password')
    authorization = emu.getLayer('DomainNameService').authorizeZoneUpdates(
        ['com', 'net'],
    )
    registry_server.setDnsAuthorization(authorization)
    registry_server.enableDnsPublication(['com', 'net'])
    emu.addLayer(registry_service)
    emu.addBinding(Binding('registry', filter=Filter(asn=151, nodeName=r'^host_'), action=Action.FIRST))

    # ------------------------------------------------------------------------
    # Registrar and domain products
    # ------------------------------------------------------------------------
    registrar_service = FossBillingRegistrarService()
    registrar_server = registrar_service.install('fossbilling')
    registrar_server.setPortForwarding(18080)
    registrar_server.setRegistry('registry')
    registrar_server.setTlds(['com', 'net'])
    registrar_server.setAdminAccount('admin@example.com', 'Aa123456')
    registrar_server.setClientAccount('user@example.com', 'Aa123456')
    registrar_server.setTldPrice('com', '11.99', '11.99', '11.99')
    registrar_server.setTldPrice('net', '11.99', '11.99', '11.99')
    # Reserve domains used by base DNS and hosting to prevent resale.
    registrar_server.setReservedDomains([
        'google.com', 'twitter.com', 'example.com', 'mastodon.com', 'ca.com',
        'fossbilling.com', 'registry.com',
    ])
    emu.addLayer(registrar_service)
    emu.addBinding(Binding('fossbilling', filter=Filter(asn=150, nodeName=r'^host_'), action=Action.FIRST))

    # ------------------------------------------------------------------------
    # Primary-secondary DNS and hosting
    # ------------------------------------------------------------------------
    dns = emu.getLayer('DomainNameService')
    dns.install('hosted-dns-primary').addZone('example.com.').setMaster()
    dns.install('hosted-dns-secondary').addZone('example.com.')
    dns_hosting = dns.addHosting('hosted-dns-primary', 'hosted-dns-secondary', domain='example.com')
    dns_hosting.addRegistrarToRateLimitWhitelist('fossbilling')
    registry_server.addNameServers(dns_hosting, epp_username=registrar_server.getEppUsername())
    registrar_server.setDnsHostings(dns_hosting)
    emu.addBinding(Binding('hosted-dns-primary', filter=Filter(asn=170, nodeName=r'^host_'), action=Action.FIRST))
    emu.addBinding(Binding('hosted-dns-secondary', filter=Filter(asn=170, nodeName=r'^host_'), action=Action.FIRST))

    # ------------------------------------------------------------------------
    # Simulated payment checkout
    # ------------------------------------------------------------------------
    fake_payment_service = FakePaymentService()
    fake_payment_server = fake_payment_service.install('fake-payment')
    fake_payment_server.setPortForwarding(18083)
    fake_payment_server.setPort(8080)
    registrar_server.setPaymentService('fake-payment')
    emu.addLayer(fake_payment_service)
    emu.addBinding(Binding('fake-payment', filter=Filter(asn=160, nodeName=r'^host_'), action=Action.FIRST))

    domain_data = DomainDataService()
    domain_data.importFile(HERE / 'domains.example.yaml')
    emu.addLayer(domain_data)

    social_as = emu.getLayer('Base').getAutonomousSystem(161)
    mastodon = social_as.createHost('mastodon').joinNetwork('net0', address='10.161.0.9')
    social_as.createHost('ca').joinNetwork('net0', address='10.161.0.4')
    social_as.createHost('alice').joinNetwork('net0', address='10.161.0.10')
    social_as.createHost('bob').joinNetwork('net0', address='10.161.0.11')
    for name, address in [('mastodon', '10.161.0.9'), ('ca', '10.161.0.4'),
                          ('fossbilling', '10.150.0.71'), ('registry', '10.151.0.71')]:
        dns.getZone('com.').addRecord(f'{name} A {address}')

    store = RootCAStore(caDomain='ca.com')
    saved_ca = HERE / '.runtime' / 'ca.com'
    if saved_ca.exists():
        Path(store.getStorePath()).rmdir()
        store.restore(str(saved_ca))
    else:
        store.initialize()
        saved_ca.parent.mkdir(parents=True, exist_ok=True)
        store.save(str(saved_ca))
        saved_ca.chmod(0o700)
    ca = CAService()
    ca.install('ca').setCAStore(store).installCACert(Filter(asn=161))
    emu.addLayer(ca)
    emu.addBinding(Binding('ca', filter=Filter(asn=161, nodeName='^ca$')))

    social = SocialMediaService()
    server = social.install('mastodon')
    server.setDomain('mastodon.com').setAcmeUrl('https://ca.com/acme/acme/directory')
    server.setPort(18443).setPortForwarding(18443)
    server.addAccount('admin', 'admin123456', email='admin@mastodon.com', admin=True)
    for name in ('alice', 'bob'):
        server.addAccount(name, name + '123456', email=name + '@mastodon.com')
        server.exportToken(name, scopes=['read:accounts', 'read:statuses', 'write:statuses'],
                           path=f'/var/lib/mastodon/agent-{name}.json')
        mastodon.addPersistentStorage('/run/agent-credentials/' + name, name='e15-socialmedia-' + name)
    emu.addLayer(social)
    emu.addBinding(Binding('mastodon', filter=Filter(asn=161, nodeName='^mastodon$')))
    configure_agents(emu, env_file)
    return emu


def use_smallstep_asset_api(emu):
    """Use official v0.26.1 asset endpoints for CAService's CLI and server."""
    assets = [
        ('cli', 'step-cli', 'amd64', 163643662),
        ('cli', 'step-cli', 'arm64', 163643661),
        ('certificates', 'step-ca', 'amd64', 163618614),
        ('certificates', 'step-ca', 'arm64', 163618611),
    ]
    for (_, kind, _), node in emu.getRegistry().getAll().items():
        if kind not in ('rs', 'rnode', 'hnode', 'csnode'):
            continue
        commands = node.getBuildCommands()
        for index, command in enumerate(commands):
            for repository, package, arch, asset_id in assets:
                filename = f'{package}_0.26.1_{arch}.deb'
                original = f'curl -O -L https://github.com/smallstep/{repository}/releases/download/v0.26.1/{filename}'
                replacement = (
                    'curl -fL --connect-timeout 10 --max-time 120 '
                    '-H "Accept: application/octet-stream" '
                    f'https://api.github.com/repos/smallstep/{repository}/releases/assets/{asset_id} '
                    f'-o {filename}'
                )
                command = command.replace(original, replacement)
            commands[index] = command


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=HERE / 'output')
    parser.add_argument('--platform', choices=['amd', 'arm'], default='amd')
    parser.add_argument('--env-file', type=Path, default=HERE / '.env')
    args = parser.parse_args(argv)
    output = args.output.resolve()
    if not args.env_file.exists():
        shutil.copy2(HERE / '.env.example', args.env_file)
        args.env_file.chmod(0o600)
    environment = read_environment(args.env_file)
    emu = build_emulator(env_file=args.env_file)
    after_render = add_model_egress(emu, environment.get('LLM_BASE_URL') or 'https://api.openai.com/v1')
    emu.render()
    use_smallstep_asset_api(emu)
    mastodon = emu.getBindingFor('mastodon')
    for name in ('alice', 'bob'):
        mastodon.appendStartCommand(
            f'install -d -m 700 -o 10001 -g 10001 /run/agent-credentials/{name} && '
            f'install -m 600 -o 10001 -g 10001 /var/lib/mastodon/agent-{name}.json '
            f'/run/agent-credentials/{name}/credentials.json')
    if after_render is not None:
        after_render()
    compiler = Docker(platform=Platform.AMD64 if args.platform == 'amd' else Platform.ARM64)
    emu.compile(compiler, str(output), override=True)
    print(f'Generated {output}; run docker compose build and docker compose up -d there.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
