#!/usr/bin/env python3
"""生成完整场景的 Docker 部署文件。 / Generate Docker deployment files for the complete environment."""
import argparse
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
SERVICES = HERE.parents[1] / 'services'
SEED_EMULATOR = HERE.parents[2] / 'seed-emulator'
sys.path.insert(0, str(SEED_EMULATOR))
sys.path.insert(0, str(SERVICES))

from DomainService import RegistryService, FossBillingService, DnsHostingService, FakePaymentService
from seedemu.core import Binding, Filter
from seedemu.compiler import Docker, Platform
from examples.internet.B02_mini_internet_with_dns.mini_internet_with_dns import build_emulator as build_b02

def build_emulator():
    """构建完整域名购买环境。 / Build the complete domain purchase environment."""

    emu = build_b02()
    # ------------------------------------------------------------------------
    # 1. Registry：注册局与 DNS 发布授权 / Registry and DNS publication authorization
    # ------------------------------------------------------------------------
    registry = RegistryService()
    server = registry.install('registry')
    server.setPortForwarding(18081)
    server.setTlds(['com', 'net'])
    server.setAdminAccount('admin@example.com', '123456')
    server.setDatabasePassword('b02a-registry-database')
    emu.addLayer(registry)
    emu.addBinding(Binding('registry', filter=Filter(asn=151, nodeName='host_1')))
    emu.getLayer('DomainNameService').authorizeRegistry(
        server,
        zones={'com': ('a-com-server', 'b-com-server'), 'net': ('a-net-server',)},
    )
    server.enableDnsPublication(['com', 'net'])

    # ------------------------------------------------------------------------
    # 2. FOSSBilling：注册商与域名商品 / Registrar and domain products
    # ------------------------------------------------------------------------
    registrar_service = FossBillingService()
    server = registrar_service.install('fossbilling')
    server.setPortForwarding(18080)
    server.setRegistry('registry')
    server.setTlds(['com', 'net'])
    server.setAdminAccount('admin@example.com', 'Aa123456')
    server.setClientAccount('user@example.com', 'Aa123456')
    server.setTldPrice('com', '11.99', '11.99', '11.99')
    server.setTldPrice('net', '11.99', '11.99', '11.99')
    # 预留基础 DNS 和托管服务使用的域名，避免再次售出。 / Reserve domains used by base DNS and hosting to prevent resale.
    server.setReservedDomains(['google.com', 'twitter.com', 'example.com'])
    server.setBrowserHosts(['localhost:18080', '127.0.0.1:18080'])
    emu.addLayer(registrar_service)
    emu.addBinding(Binding('fossbilling', filter=Filter(asn=150, nodeName='host_1')))

    # ------------------------------------------------------------------------
    # 3. DNS Hosting：主从 DNS 与托管服务 / Primary-secondary DNS and hosting
    # ------------------------------------------------------------------------
    dns = emu.getLayer('DomainNameService')
    dns.install('hosted-dns-primary').addZone('example.com.').setMaster()
    dns.install('hosted-dns-secondary').addZone('example.com.')
    emu.addBinding(Binding('hosted-dns-primary', filter=Filter(asn=170, nodeName='host_0')))
    emu.addBinding(Binding('hosted-dns-secondary', filter=Filter(asn=170, nodeName='host_1')))
    dns_hosting_service = DnsHostingService()
    hosting = dns_hosting_service.install('dns-hosting')
    hosting.setNameServers('hosted-dns-primary', 'hosted-dns-secondary', domain='example.com')
    hosting.setRegistrar('fossbilling')
    emu.addLayer(dns_hosting_service)
    # API 与主 DNS 共用主机；从节点由托管实例关联，无需额外 Host。
    # The API shares the primary DNS host; the hosting instance references the secondary without creating hosts.
    emu.addBinding(Binding('dns-hosting', filter=Filter(asn=170, nodeName='host_0', allowBound=True)))

    # ------------------------------------------------------------------------
    # 4. FakePayment：模拟支付收银台 / Simulated payment checkout
    # ------------------------------------------------------------------------
    fake_payment_service = FakePaymentService()
    checkout = fake_payment_service.install('fake-payment')
    checkout.setPortForwarding(18083)
    checkout.setRegistrar('fossbilling').setPort(8080)
    checkout.setBrowserUrls({'localhost:18080': 'http://localhost:18083/pay',
                             '127.0.0.1:18080': 'http://127.0.0.1:18083/pay'})
    emu.addLayer(fake_payment_service)
    emu.addBinding(Binding('fake-payment', filter=Filter(asn=160, nodeName='host_1')))
    return emu


def main(argv=None):
    """渲染场景并生成部署文件，不构建或启动容器。 / Render and generate deployment files without building or starting containers."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=HERE / 'output')
    parser.add_argument('--platform', choices=['amd', 'arm'], default='amd')

    args = parser.parse_args(argv)
    output = args.output.resolve()
    try:
        emu = build_emulator()
        emu.render()
        emu.compile(Docker(platform=Platform.AMD64 if args.platform == 'amd' else Platform.ARM64),
                    str(output), override=True)
        if not (output / 'docker-compose.yml').is_file():
            raise RuntimeError(f'Missing {output / "docker-compose.yml"}')
        return 0
    except (OSError, RuntimeError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
