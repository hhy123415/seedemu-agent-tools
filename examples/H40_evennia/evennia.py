#!/usr/bin/env python3
"""Deploy Evennia and InternetMap on an example-local compact Internet."""
import argparse
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))

from bundles.EvenniaBundle import EvenniaBundle
from seedemu.compiler import Docker, Platform
from seedemu.containerBundle import InternetMap
from seedemu.core import Binding, Emulator, Filter
from seedemu.layers import Base, Ebgp, PeerRelationship, Routing
from seedemu.services import DomainNameCachingService, DomainNameService

ASN = 150
WORLD_ADDRESS = '10.150.0.10'
GATEWAY = '10.150.0.254'
DNS_AUTHORITY = '10.150.0.53'
DNS_RESOLVER = '10.150.0.54'


def build_world():
    """Build two ASes, one exchange and local DNS without importing H00."""
    emu = Emulator()
    base = Base().setNameServers([DNS_RESOLVER])
    ebgp = Ebgp()

    # 两个 AS 直接建立 eBGP 邻接，无需独立路由服务器或额外骨干 AS。
    base.createInternetExchange(100, prefix='10.100.0.0/24', create_rs=False)
    world_as = base.createAutonomousSystem(ASN)
    world_as.createNetwork('net0', prefix='10.150.0.0/24')
    router = world_as.createRouter('router0').setDisplayName('Evennia Router')
    router.joinNetwork('net0', GATEWAY).joinNetwork('ix100', '10.100.0.150')

    outside = base.createAutonomousSystem(99999)
    outside.createRealWorldRouter(
        'internet-egress', prefixes=['0.0.0.0/1', '128.0.0.0/1']
    ).joinNetwork('ix100', '10.100.0.99')
    ebgp.addPrivatePeering(100, 99999, ASN, PeerRelationship.Provider)
    for layer in (base, Routing(), ebgp):
        emu.addLayer(layer)

    # 根、com 和 evennia.com 合并部署在一台权威 DNS 上，另设递归解析器。
    authority = DomainNameService()
    world_as.createHost('dns_authority').joinNetwork('net0', DNS_AUTHORITY)
    server = authority.install('dns_authority').setMaster()
    for zone in ('.', 'com.', 'evennia.com.'):
        server.addZone(zone)
    authority.getZone('evennia.com.').addRecord('@ A ' + WORLD_ADDRESS)
    emu.addLayer(authority)
    emu.addBinding(Binding('dns_authority', filter=Filter(asn=ASN, nodeName='dns_authority')))

    resolver = DomainNameCachingService()
    world_as.createHost('dns_resolver').joinNetwork('net0', DNS_RESOLVER)
    resolver.install('dns_resolver')
    emu.addLayer(resolver)
    emu.addBinding(Binding('dns_resolver', filter=Filter(asn=ASN, nodeName='dns_resolver')))
    return emu


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=HERE / 'output')
    parser.add_argument('--state', type=Path, help='Persist game directory outside output')
    args = parser.parse_args()
    output = args.output.resolve()
    if args.state:
        state = args.state.resolve()
        if state == output or output in state.parents or state in output.parents:
            parser.error('state and output directories must not contain each other')
    emu = build_world()
    try:
        bundle = (EvenniaBundle(emu, name='evennia')
                  .setDataVolume('h40-evennia-data')
                  .setSuperuser('admin', 'emuvista')
                  .importMap(HERE / 'evennia-map.json', mode='replace', spawn='room-42')
                  .enableHostAccess(web_port=4001, websocket_port=4002, telnet_port=4000))
        if args.state:
            bundle.setSavePath(args.state)
    except ValueError as error:
        parser.error(str(error))

    emu.render()
    bundle.addInternalNetwork(str(ASN), 'net0', [WORLD_ADDRESS], GATEWAY)
    bundle.getContainer('server').updateServiceConfig({'dns': [DNS_RESOLVER]})
    compiler = Docker(platform=Platform.AMD64, internetMapEnabled=False)
    bundle.registerVolumes(compiler)
    compiler.addContainerBundle(bundle)
    internet_map = InternetMap(emu)
    internet_map.setPorts([8081, 8080, 8082])
    compiler.addContainerBundle(internet_map)
    output.parent.mkdir(parents=True, exist_ok=True)
    emu.compile(compiler, str(output), override=True)
    print(f'Generated {output / "docker-compose.yml"}')


if __name__ == '__main__':
    main()
