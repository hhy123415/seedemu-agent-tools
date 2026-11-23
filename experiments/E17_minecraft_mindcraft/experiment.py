#!/usr/bin/env python3
"""Generate SEED mini Internet with Minecraft, Mindcraft agents and PaymentBundle."""
import argparse
import json
from pathlib import Path
import shutil
import sys

import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))

from bundles.MinecraftBundle import MinecraftBundle, MINECRAFT_VERSION
from services.MinecraftAgentService import MinecraftAgentService
from seedemu.compiler import Docker, Platform
from seedemu.containerBundle import InternetMap
from seedemu.containerBundle.ContainerBundle import PreparedContainer
from seedemu.core import Emulator
from seedemu.layers import Base, Routing, Ebgp, PeerRelationship
from bundles.PaymentBundle import PaymentBundle
OP_NAMES = ('seed',)

# 实验支付社区和账号，同时用于生成每个 agent 独立的支付身份。
PAYMENT_CONFIGURATION = {
    'groups': [{
        'code': 'MINE', 'name': 'Minecraft Community',
        'currency': {'name': 'Minecraft Credit', 'symbol': 'MC', 'rate': 1},
        'users': [
            {'name': 'Alice', 'email': 'alice@mail.com', 'password': 'payment-demo', 'balance': 100},
            {'name': 'Bob', 'email': 'bob@mail.com', 'password': 'payment-demo', 'balance': 100},
        ],
    }],
}

# 人设与任务在此维护；具体路线、交易数量和价格由 agent 观察并协商决定。
PERSONAS = {
    'Alice': {
        'persona': (
            # Alice 自主伐木并以丢弃物品的方式把原木交给 Bob。
            'You are Alice, a resident working as a woodcutter. Your current task is to find naturally growing trees, '
            'chop them for logs, and give the collected logs to Bob by dropping them nearby for Bob to pick up. '
            'Coordinate your location with Bob, wait for him to be close enough before dropping logs, and discuss '
            'the wood type, quantity and price with him before delivery. Choose practical batches based on your observations. '
            # 交付和收款依据观察及回执确认，不把口头声明当作结果。
            'Check your inventory before and after dropping logs, tell Bob what you dropped, and ask him to confirm what he actually received. '
            'Your payment account is alice@mail.com and the currency is MC (100 minor units = 1 MC). '
            'Ask Bob to pay the agreed amount for the logs he received; use payment tools to check your balance or a receipt '
            'when confirming payment. Do not claim delivery or payment succeeded without evidence. '
            # 不得破坏建筑；只选择可确认的天然树木，不确定时先询问。
            'Never damage buildings or player-built structures, including walls, roofs, floors, fences, paths, furnishings and storage. '
            'Logs or planks belonging to a building are not trees to harvest. Do not take wood from chests or other residents. '
            'Consult the region map when needed and inspect the surroundings; harvest only clearly natural trees away from structures. '
            'If unsure whether a tree or block belongs to a build, leave it intact and ask. Do not break structures to navigate. '
            # 允许中文对话协调工作，避免无意义的相互应答。
            'Talk with Bob in Chinese to coordinate movement, delivery and payment. Answer relevant questions and share useful updates, '
            'but avoid repeated greetings or acknowledgement loops. Stay safe and use no cheats.'
        ),
        'auto_start': True,
        'resume_on_restart': True,
        'cooldown_ms': 5000,
        'decision_interval_ms': 60000,
    },
    'Bob': {
        'persona': (
            # Bob 跟随 Alice，观察并拾取 Alice 实际丢下的原木。
            'You are Bob, a resident buying logs from Alice. Your current task is to follow Alice while she gathers wood, '
            'stay close enough to receive her dropped logs without obstructing her, and pick up the logs she drops for you. '
            'If you lose sight of Alice, ask her location and coordinate a meeting. Discuss the wood type, quantity and price '
            'with Alice before delivery; choose and negotiate these details yourself. '
            # 收到木头后再付款，金额由双方约定和实际收货数量决定。
            'Observe your inventory before and after pickup to determine the type and quantity actually received. '
            'Do not treat Alice saying she dropped logs as proof that you received them. After receiving her logs, '
            'pay Alice the agreed amount for the received batch using payment.transfer. Your account is bob@mail.com; '
            'Alice is alice@mail.com. The currency is MC and 100 minor units = 1 MC. Check your balance when needed. '
            'Use a fresh UUID for each distinct payment, keep the same UUID for retries of that payment, and check payment.receipt '
            'after an uncertain result before retrying. Do not pay twice for the same received batch. Tell Alice the received quantity '
            'and the payment result, including the transfer ID. If the price, delivery or payment is unclear, discuss it with Alice. '
            # 不得拆建筑、挖墙跟随或从他人容器中取物。
            'Never damage buildings or player-built structures, including walls, roofs, floors, fences, paths, furnishings and storage. '
            'Do not break structures to follow Alice, and do not take items from chests or other residents. '
            'Use existing entrances and safe routes; if blocked, ask Alice to wait or meet elsewhere. '
            # 允许中文沟通，避免仅为了回复而不断对话。
            'Talk with Alice in Chinese to coordinate following, pickup and payment. Answer relevant questions and share useful updates, '
            'but avoid repeated greetings or acknowledgement loops. Stay safe and use no cheats.'
        ),
        'auto_start': True,
        'resume_on_restart': True,
        'cooldown_ms': 5000,
        'decision_interval_ms': 60000,
    },
}


def build_network():
    """Three application ASes and one transit/Internet gateway; no example topology."""
    emu = Emulator()
    base, routing, ebgp = Base(), Routing(), Ebgp()
    # 一个交换网络承载三条业务 AS 到出口 AS 的 eBGP 邻接，无需路由服务器。
    base.createInternetExchange(100, prefix='10.100.0.0/24', create_rs=False)
    for asn, label in [(150, 'Payment'), (170, 'Minecraft'), (171, 'Mindcraft')]:
        system = base.createAutonomousSystem(asn)
        system.createNetwork('net0', prefix=f'10.{asn}.0.0/24')
        router = system.createRouter('router0')
        router.setDisplayName(label + ' router')
        router.joinNetwork('net0', f'10.{asn}.0.254')
        router.joinNetwork('ix100', f'10.100.0.{asn}')
    outside = base.createAutonomousSystem(99999)
    egress = outside.createRealWorldRouter(
        'internet-egress', prefixes=['0.0.0.0/1', '128.0.0.0/1']
    ).joinNetwork('ix100', '10.100.0.99')
    # 跨 AS 流量保留源地址；豁免置于公网 MASQUERADE 规则之前。
    for subnet in ('10.150.0.0/24', '10.170.0.0/24', '10.171.0.0/24'):
        egress.appendStartCommand(
            f'iptables -t nat -C POSTROUTING -d {subnet} -j RETURN 2>/dev/null '
            f'|| iptables -t nat -I POSTROUTING 1 -d {subnet} -j RETURN')
    for asn in (150, 170, 171):
        # 出口 AS 为 provider，向各业务 AS 发布公网及其他业务子网路由。
        ebgp.addPrivatePeering(100, 99999, asn, PeerRelationship.Provider)
    for layer in (base, routing, ebgp):
        emu.addLayer(layer)
    return emu


def compile_network(output, state_path, payment_configuration, payment_port):
    emu = build_network()
    emu.render()
    payment = (PaymentBundle(emu)
               .setHostname('payment.com').enableHostAccess(payment_port)
               .setSavePath(state_path).setInitialConfiguration(payment_configuration))
    payment.addInternalNetwork('150', 'net0',
                              [f'10.150.0.{10+i}' for i in range(len(payment.getContainers()))],
                              '10.150.0.254')
    payment.addEtcHostsRecord('payment.com', '10.150.0.10')
    payment.addEtcHostsRecord('minecraft.com', '10.170.0.10')
    compiler = Docker(platform=Platform.AMD64)
    compiler.addContainerBundle(payment)
    internet_map = InternetMap(emu)
    internet_map.setPorts([8081, 8080, 8082])
    compiler.addContainerBundle(internet_map)
    emu.compile(compiler, str(output), override=True)
    return emu, yaml.safe_load((output / 'docker-compose.yml').read_text())


def attach(emu, output, service, *, asn, address, context, entrypoint):
    """Use SEED address validation and map labels, preserving existing app images."""
    node = PreparedContainer(name=service['container_name'], emulator=emu)
    node.joinInternalNetwork(str(asn), 'net0', address, service['container_name'], f'10.{asn}.0.254')
    service['networks'] = node._service['networks']
    service['labels'] = node._service['labels']
    service['cap_add'] = ['NET_ADMIN']
    # 实验域名使用本地映射，公网模型和下载域名继续由 Docker DNS 解析。
    service['extra_hosts'] = ['minecraft.com:10.170.0.10', 'payment.com:10.150.0.10']
    service['entrypoint'] = ['sh', '/network-start.sh']
    context = output / context
    # Alice/Bob 共享构建目录，网关相同，因此使用相同的路由包装脚本。
    (context / 'network-start.sh').write_text('#!/bin/sh\nset -eu\n'
        + '\n'.join(node._getDefaultRouteCommands()) + f'\nexec sh {entrypoint} "$@"\n')
    dockerfile = context / 'Dockerfile'
    marker = '\n# SEED network attachment\n'
    original = dockerfile.read_text().split(marker)[0]
    dockerfile.write_text(original + marker
        + 'RUN apt-get update && apt-get install -y --no-install-recommends iproute2 && rm -rf /var/lib/apt/lists/*\n'
        + 'COPY network-start.sh /network-start.sh\n')


def generate(output, env_file, host_port=25566, ui_port=18090, bob_ui_port=18091, payment_port=8443):
    output.mkdir(parents=True, exist_ok=True)
    # 已有数据卷的物理名称是持久化标识，重命名逻辑服务时仍复用原存档。
    volume_names = {name: name for name in ('mindcraft-world', 'mindcraft-alice', 'mindcraft-bob')}
    previous = output / 'docker-compose.yml'
    if previous.exists():
        old = yaml.safe_load(previous.read_text())
        for service, destination, logical in (
                ('minecraft', '/data', 'mindcraft-world'),
                ('alice', '/app/bots/Alice', 'mindcraft-alice'),
                ('bob', '/app/bots/Bob', 'mindcraft-bob')):
            for mount in old.get('services', {}).get(service, {}).get('volumes', []):
                if isinstance(mount, str) and mount.endswith(':' + destination):
                    source = mount.split(':', 1)[0]
                    if source in old.get('volumes', {}):
                        volume_names[logical] = old['volumes'][source].get('name', source)
        archive = HERE / '.runtime' / 'previous-deployment.yml'
        archive.parent.mkdir(exist_ok=True)
        shutil.copyfile(previous, archive)
    # 编译器重建 output；持久化支付状态和世界均放在 output 外。
    emu, infrastructure = compile_network(output, HERE / '.runtime' / 'payment-state',
                                         PAYMENT_CONFIGURATION, payment_port)
    regions = HERE / 'map' / 'regions'
    minecraft = (MinecraftBundle()
                 .setWorld(HERE / 'world')
                 .setRegionPath(regions)
                 .setDataVolume('mindcraft-world')
                 .setOperators(OP_NAMES)
                 .enableHostAccess(host_port)
                 .configureApplication({'MOTD': 'Mindcraft - Alice'}))
    regions.mkdir(parents=True, exist_ok=True)
    # JSON 仅为自动生成的运行时配置，放在镜像构建目录之外。
    persona_dir = output / 'personas'
    persona_dir.mkdir(parents=True, exist_ok=True)
    for name, config in PERSONAS.items():
        (persona_dir / f'{name.lower()}.json').write_text(
            json.dumps(config, ensure_ascii=False, indent=2) + '\n')
    payment_tools = PaymentBundle().setHostname('payment.com').setInitialConfiguration(PAYMENT_CONFIGURATION).getAgentTools()
    agents = (MinecraftAgentService(env_file, minecraft_host='minecraft.com', minecraft_version=MINECRAFT_VERSION)
              .setRegionPath(regions)
              .registerTools(payment_tools))
    for user in PAYMENT_CONFIGURATION['groups'][0]['users']:
        agents.addAgent(user['name'], persona_file=persona_dir / (user['name'].lower() + '.json'),
                        ui_port=ui_port if user['name'] == 'Alice' else bob_ui_port,
                        accounts={'email': {'email': user['email']},
                                  'payment': {'email': user['email'], 'password': user['password'],
                                              'group': 'MINE', 'currency': 'MC'}},
                        tools=['payment.balance', 'payment.transfer', 'payment.receipt'])
    compose = agents.prepare(output, context_name='alice', minecraft_service='minecraft')
    # 本实验允许 Alice 和 Bob 相互听到并回复公开聊天。
    for role in ('alice', 'bob'):
        compose['services'][role]['environment']['MINDCRAFT_IGNORED_PLAYERS'] = ''
    compose['services'] = {
        'minecraft': minecraft.prepare(output, container_name='minecraft-server'),
        **compose['services'],
    }
    # 豁免所有聊天/命令前缀的刷屏检查；由镜像在每次启动时应用，避免配置下载覆盖。
    compose['services']['minecraft']['environment']['PATCH_DEFINITIONS'] = '/e17-server-patches.json'
    compose['services']['minecraft']['volumes'].append(
        f'{HERE / "server-patches.json"}:/e17-server-patches.json:ro')
    attach(emu, output, compose['services']['minecraft'], asn=170, address='10.170.0.10',
           context='server', entrypoint='/semantic-start.sh')
    for role, address in [('alice', '10.171.0.10'), ('bob', '10.171.0.11')]:
        attach(emu, output, compose['services'][role], asn=171, address=address,
               context='alice', entrypoint='/mindcraft/start.sh')
    infrastructure['services'].update(compose['services'])
    compose['services'] = infrastructure['services']
    # 当前支付前端和网关镜像提供 curl，不提供 wget；避免健康检查误报。
    for role, path in [('payment-app', '/'), ('payment-gateway', '/healthz')]:
        compose['services'][role]['healthcheck']['test'] = [
            'CMD', 'curl', '-fsS', '-o', '/dev/null', f'http://127.0.0.1{path}']
    compose['networks'] = infrastructure['networks']
    compose['volumes'] = {name: {'name': physical} for name, physical in volume_names.items()}
    (output / 'docker-compose.yml').write_text(yaml.safe_dump(compose, sort_keys=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=HERE / 'output')
    parser.add_argument('--env-file', type=Path, default=HERE / '.env')
    parser.add_argument('--host-port', type=int, default=25566)
    parser.add_argument('--ui-port', type=int, default=18090)
    parser.add_argument('--payment-port', type=int, default=8443)
    parser.add_argument('--bob-ui-port', type=int, default=18091)
    args = parser.parse_args()
    if not all(1 <= p <= 65535 for p in (args.host_port, args.ui_port, args.bob_ui_port, args.payment_port)):
        parser.error('ports must be between 1 and 65535')
    if len({args.host_port, args.ui_port, args.bob_ui_port, args.payment_port, 8080, 8081, 8082}) != 7:
        parser.error('server, UI, payment and InternetMap ports must be distinct')
    output, env_file = args.output.resolve(), args.env_file.resolve()
    if env_file == output or output in env_file.parents:
        parser.error('env-file must be outside the generated output directory')
    if not env_file.exists():
        env_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(HERE / '.env.example', env_file)
        env_file.chmod(0o600)
    generate(output, env_file, args.host_port, args.ui_port, args.bob_ui_port, args.payment_port)
    print(f'Generated {output}; configure credentials in {env_file} before starting Alice.')


if __name__ == '__main__':
    main()
