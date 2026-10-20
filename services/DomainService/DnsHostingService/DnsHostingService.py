"""封装主从 BIND API 与 FOSSBilling DNS Hosting 集成。 / Encapsulate primary/secondary BIND APIs and FOSSBilling DNS Hosting integration."""
import re
import json
import shlex

from seedemu.core import Server, Service
from ..FossBillingService import FossBillingServer
from .dns_install import install_nameserver, install_extension
from .template import DnsFileTemplates


class DnsHostingServer(Server):
    """一个实例管理一对已有 DNS 节点及一个注册商的托管产品。 / An instance manages two existing DNS nodes and one registrar's hosting product."""

    def __init__(self):
        """设置默认虚拟节点和托管域名。 / Set default virtual nodes and the hosting domain."""
        super().__init__()
        self._primary = 'hosted-dns-primary'
        self._secondary = 'hosted-dns-secondary'
        self._domain = 'example.com'
        self._registrar = 'fossbilling'
        self._nodes = None
        self.appendClassName('DnsHostingService')

    def setNameServers(self, primary, secondary, domain='example.com'):
        """选择 DNS 虚拟节点及其已有静态区域。 / Select DNS virtual nodes and their existing static zone."""
        if any(not isinstance(value, str) or not value for value in (primary, secondary, domain)) or primary == secondary:
            raise ValueError('Distinct primary and secondary DNS virtual nodes are required')
        domain = domain.lower().rstrip('.')
        label = r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?'
        if not re.fullmatch(label + r'\.' + label, domain):
            raise ValueError('Hosting domain must be a second-level ASCII domain')
        self._primary, self._secondary, self._domain = primary, secondary, domain
        return self

    def setRegistrar(self, virtual_node):
        """选择已安装的 FOSSBilling 注册商实例。 / Select an installed FOSSBilling registrar instance."""
        if not isinstance(virtual_node, str) or not virtual_node:
            raise ValueError('A registrar virtual node is required')
        self._registrar = virtual_node
        return self

    def configure(self, emulator, node):
        """解析主从及注册商绑定，拒绝冲突的区域或主机。 / Resolve DNS and registrar bindings and reject conflicting zones or hosts."""
        dns = emulator.getLayer('DomainNameService')
        for vnode in (self._primary, self._secondary):
            if vnode not in dns.getPendingTargets():
                raise ValueError(f'{vnode} must be installed by DomainNameService')
            server = dns.getPendingTargets()[vnode]
            if server.getZones() != [self._domain + '.'] or server.getIncludePath(self._domain + '.') is not None:
                raise ValueError('Hosted DNS nodes must exclusively host the selected zone without custom includes')
        primary = emulator.getBindingFor(self._primary)
        secondary = emulator.getBindingFor(self._secondary)
        registrar = emulator.getServerByVirtualNodeName(self._registrar)
        if not isinstance(registrar, FossBillingServer):
            raise ValueError('The registrar must use FossBillingService')
        registrar_node = emulator.getBindingFor(self._registrar)
        if node is not primary or primary is secondary or registrar_node in (primary, secondary):
            raise ValueError('Bind DNS hosting to the primary DNS host; primary, secondary, and registrar must be distinct')
        if self._domain not in registrar.getReservedDomains():
            raise ValueError('Reserve the hosting domain on the registrar before rendering')
        primary_ip = str(primary.getInterfaces()[0].getAddress())
        secondary_ip = str(secondary.getInterfaces()[0].getAddress())
        if dns.getMasterIp().get(self._domain + '.') != [primary_ip]:
            raise ValueError('Set only the primary DNS node as master for the hosting zone')
        records = dns.getZone(self._domain + '.').getRecords()
        if (f'ns1.{self._domain}. A {primary_ip}' not in records
                or f'ns2.{self._domain}. A {secondary_ip}' not in records):
            raise ValueError('Install primary before secondary so ns1/ns2 match their bound addresses')
        self._registry_node = emulator.getBindingFor(registrar._registry)
        self._nodes = primary, secondary, registrar_node
        self._settings = {
            'domain': self._domain, 'registrar': registrar.getEppUsername(),
            'primary': str(primary.getInterfaces()[0].getAddress()),
            'secondary': str(secondary.getInterfaces()[0].getAddress()),
            'ns1': 'ns1.' + self._domain, 'ns2': 'ns2.' + self._domain,
            'soaemail': 'hostmaster@' + self._domain,
        }

    def install(self, node):
        """安装主从 API 和扩展，保留 DomainNameService 的区域管理。 / Install both APIs and the extension while retaining DomainNameService zone management."""
        if self._nodes is None:
            raise RuntimeError('Configure DNS hosting through emulator.render() first')
        primary, secondary, registrar = self._nodes
        for role, host in [('primary', primary), ('secondary', secondary)]:
            host.setDisplayName(self._settings['ns1' if role == 'primary' else 'ns2'])
            install_nameserver(host, role, self._settings[role], self._settings['secondary'],
                               str(registrar.getInterfaces()[0].getAddress()), self._domain)
        install_extension(registrar, self._settings)
        # Registry 已完成本地注册商及父域名初始化，再登记 NS。 / Register NS after local registrar and parent-domain initialization.
        registry = self._registry_node
        directory = '/opt/b02c/hosts-' + self._domain
        registry.setFile(directory + '.php', DnsFileTemplates['setup-hosts-registry.php'])
        environment = {
            'B02C_HOSTS': json.dumps([[self._settings['ns1'], self._settings['primary']],
                                     [self._settings['ns2'], self._settings['secondary']]]),
            'B02C_REGISTRAR': self._settings['registrar'],
            'B02C_PARENT': self._domain, 'B02C_CHECK_ONLY': '0',
        }
        exports = ''.join('export ' + key + '=' + shlex.quote(value) + '\n'
                          for key, value in environment.items())
        marker = '/run/registry-hosts-' + self._domain
        registry.setFile(directory + '.sh', '#!/bin/sh\nset -e\n'
                         + 'rm -f ' + marker + '.ready ' + marker + '.failed\n'
                         + "trap 'touch " + marker + ".failed' EXIT\n"
                         + exports + 'php8.5 ' + directory + '.php\n'
                         + 'touch ' + marker + '.ready\ntrap - EXIT\n')
        registry.appendStartCommand('sh ' + directory + '.sh > /var/log/registry-hosts-'
                                    + self._domain + '.log 2>&1')

    def print(self, indent):
        """返回实例说明。 / Return the instance description."""
        return ' ' * indent + 'DNS Hosting server pair\n'


class DnsHostingService(Service):
    """在已绑定的 DNS 节点上增加托管 API。 / Add hosting APIs to already-bound DNS nodes."""

    def __init__(self):
        """声明 DNS、注册商和 Registry 依赖。 / Declare DNS, registrar, and Registry dependencies."""
        super().__init__()
        for name in ('Base', 'Routing', 'DomainNameService', 'FossBillingService'):
            self.addDependency(name, False, False)

    def configure(self, emulator):
        """配置每一对节点，每个注册商只绑定一对托管 DNS。 / Configure each pair with one hosting pair per registrar."""
        registrars, dns_nodes = set(), set()
        for vnode, server in self._pending_targets.items():
            server.configure(emulator, emulator.getBindingFor(vnode))
            pair = server._nodes[:2]
            if server._registrar in registrars or any(id(node) in dns_nodes for node in pair):
                raise ValueError('DNS pairs and registrar hosting configurations must not overlap')
            registrars.add(server._registrar)
            dns_nodes.update(id(node) for node in pair)
        super().configure(emulator)

    def _createServer(self):
        """创建托管 DNS 实例。 / Create a DNS hosting instance."""
        return DnsHostingServer()

    def getName(self):
        """返回服务名称。 / Return the service name."""
        return 'DnsHostingService'

    def print(self, indent):
        """返回服务层说明。 / Return the service layer description."""
        return ' ' * indent + 'DnsHostingServiceLayer\n'
