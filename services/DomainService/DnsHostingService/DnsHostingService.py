"""Native DNS subclass with hosting APIs, FOSSBilling integration, and dynamic update authorization.
"""
import base64
import json
import re
import secrets
import shlex
from typing import List

from seedemu.core import Hook
from seedemu.services import DomainNameService, DomainNameServer
from seedemu.mergers.DefaultDomainNameServiceMerger import DefaultDomainNameServiceMerger
from ..FossBillingService import FossBillingServer
from .dns_install import install_nameserver, install_extension
from .template import DnsFileTemplates


class _DnsHostingPair:
    """An instance manages two existing DNS nodes and one registrar's hosting product."""

    def __init__(self):
        """Set default virtual nodes and the hosting domain."""
        self._primary = 'hosted-dns-primary'
        self._secondary = 'hosted-dns-secondary'
        self._domain = 'example.com'
        self._registrar = 'fossbilling'
        self._nodes = None

    def setNameServers(self, primary, secondary, domain='example.com'):
        """Select DNS virtual nodes and their existing static zone."""
        if any(not isinstance(value, str) or not value for value in (primary, secondary, domain)) or primary == secondary:
            raise ValueError('Distinct primary and secondary DNS virtual nodes are required')
        domain = domain.lower().rstrip('.')
        label = r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?'
        if not re.fullmatch(label + r'\.' + label, domain):
            raise ValueError('Hosting domain must be a second-level ASCII domain')
        self._primary, self._secondary, self._domain = primary, secondary, domain
        return self

    def setRegistrar(self, virtual_node):
        """Select an installed FOSSBilling registrar instance."""
        if not isinstance(virtual_node, str) or not virtual_node:
            raise ValueError('A registrar virtual node is required')
        self._registrar = virtual_node
        return self

    def configure(self, emulator):
        """Resolve DNS and registrar bindings and reject conflicting zones or hosts."""
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
        if primary is secondary or registrar_node in (primary, secondary):
            raise ValueError('Primary, secondary, and registrar must be distinct')
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

    def install(self):
        """Install both APIs and the extension while retaining DomainNameService zone management."""
        if self._nodes is None:
            raise RuntimeError('Configure DNS hosting through emulator.render() first')
        primary, secondary, registrar = self._nodes
        for role, host in [('primary', primary), ('secondary', secondary)]:
            host.setDisplayName(self._settings['ns1' if role == 'primary' else 'ns2'])
            install_nameserver(host, role, self._settings[role], self._settings['secondary'],
                               str(registrar.getInterfaces()[0].getAddress()), self._domain)
        install_extension(registrar, self._settings)
        # Register NS after local registrar and parent-domain initialization.
        registry = self._registry_node
        directory = '/opt/dns-hosting/hosts-' + self._domain
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


class DnsUpdateAuthorization:
    """    DNS update credentials populated by DNS rendering and read by publishers.
    """

    def __init__(self, zones):
        self.__zones = tuple(zones)
        self.__credentials = {}

    def getZones(self):
        """Return authorized zone names."""
        return self.__zones

    def getCredentials(self, zone):
        """Read the address and TSIG key after rendering."""
        if zone not in self.__credentials:
            raise RuntimeError('DNS authorization is not ready; render DomainNameService first')
        return self.__credentials[zone]

    def _setCredentials(self, zone, address, key):
        """Populate credentials from the DNS service."""
        self.__credentials[zone] = (address, key)


class DnsHostingService(DomainNameService):
    """    Extend native DNS with hosting APIs and publisher-independent update authorizations.
    """

    def __init__(self, autoNameServer=True):
        """Preserve base initialization and track authorizations."""
        super().__init__(autoNameServer)
        self._update_authorizations = []
        self._hosting = []

    def addHosting(self, primary, secondary, domain='example.com'):
        """Add hosting to existing DNS nodes without another virtual node."""
        hosting = _DnsHostingPair().setNameServers(primary, secondary, domain)
        self._hosting.append(hosting)
        return hosting

    def configure(self, emulator):
        """Configure native DNS and defer hosting installation until the registrar is rendered."""
        super().configure(emulator)
        if self._hosting:
            emulator.getLayer('FossBillingService')
            emulator.addHook(_DnsHostingHook(self))

    def getZoneServerNames(self, domain: str) -> List[str]:
        """!
        @brief Get the names of servers hosting the given zone. This only works
        if the server was installed by using the "installByName" call.

        @param domain domain.

        @returns list of tuple of (node name, asn)
        """
        info = []
        targets = self.getPendingTargets()

        for (vnode, sobj) in targets.items():
            server: DomainNameServer = sobj

            hit = False

            for zone in server.getZones():
                if zone == domain:
                    info.append(vnode)
                    hit = True
                    break
            
            if hit: continue
        
        return info

    def authorizeZoneUpdates(self, zones):
        """        Create a publisher-independent authorization for NS/A/AAAA updates below
        each zone, protecting its apex and name servers. Pass zone names only; DNS
        discovers their servers and primary from its own configuration. Returns credentials
        resolved during DNS rendering; consumers must render after this layer.
        """
        normalized, servers, hosted = {}, {}, {}
        for value in zones:
            zone_name = value.removesuffix('.').lower()
            if (len(zone_name) > 253 or not all(re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label)
                                              for label in zone_name.split('.'))):
                raise ValueError(f'Invalid zone: {value}')
            names = self.getZoneServerNames(zone_name + '.')
            if not names:
                raise ValueError(f'No DNS servers host {zone_name}.')
            normalized[zone_name] = tuple(names)
            for name in names:
                server = self._pending_targets[name]
                if server.getIncludePath(zone_name + '.') is not None:
                    raise ValueError(f'{name} already has a custom include for {zone_name}.')
                servers[name] = server
                hosted.setdefault(name, set()).add(zone_name + '.')
        for name, server in servers.items():
            if {zone.rstrip('.').lower() + '.' for zone in server.getZones()} != hosted[name]:
                raise ValueError(f'All zones hosted by {name} must be included in zones')
        # Mutate includes only after complete validation.
        for zone_name, names in normalized.items():
            for name in names:
                servers[name].setInclude(zone_name + '.', f'/etc/bind/update-{zone_name}.conf')
        authorization = DnsUpdateAuthorization(zone_name + '.' for zone_name in normalized)
        self._update_authorizations.append((authorization, normalized))
        return authorization

    def __renderUpdateAuthorizations(self, emulator):
        """Render DNS authorization and populate credentials."""
        def new_key(identity):
            secret = base64.b64encode(secrets.token_bytes(32)).decode('ascii')
            return f'key "{identity}" {{ algorithm hmac-sha256; secret "{secret}"; }};\n'

        for authorization, zones in self._update_authorizations:
            for zone_name, vnodes in zones.items():
                zone = zone_name + '.'
                nodes = [emulator.getServerByVirtualNodeName(name).getNode() for name in vnodes]
                if len(nodes) > 1:
                    master_ips = self.getMasterIp().get(zone, [])
                    primaries = [node for node in nodes
                                 if str(node.getInterfaces()[0].getAddress()) in master_ips]
                    if len(primaries) != 1:
                        raise ValueError(f'{zone} requires exactly one configured DNS primary')
                    nodes = primaries + [node for node in nodes if node is not primaries[0]]
                primary = nodes[0]
                primary_ip = str(primary.getInterfaces()[0].getAddress())
                publish_id, transfer_id = f'{zone_name}-publisher', f'{zone_name}-zone-transfer'
                bind_path = f'/etc/bind/keys/{zone_name}-publisher.key'
                transfer_path = f'/etc/bind/keys/{zone_name}-transfer.key'
                zone_path = f'/etc/bind/zones/{zone}'
                config_path = f'/etc/bind/update-{zone_name}.conf'
                publish_key, transfer_key = new_key(publish_id), new_key(transfer_id)
                records = self.getZone(zone).getRecords()

                # Protect the apex and name server records, including explicit TTL and IN fields.
                protected = {zone}
                for record in records:
                    fields = record.split(';', 1)[0].split()
                    upper = [field.upper() for field in fields]
                    if fields and fields[0].lower() in ('@', zone) and 'NS' in upper:
                        index = upper.index('NS')
                        if index + 1 < len(fields):
                            name = fields[index + 1].lower()
                            protected.add(name if name.endswith('.') else name + '.' + zone)
                policy = '\n'.join(f'    deny {publish_id} name {name} ANY;' for name in sorted(protected))
                policy += f'\n    grant {publish_id} subdomain {zone} NS A AAAA;'
                transfer = '    allow-transfer { none; };\n    notify no;'
                if len(nodes) > 1:
                    secondary_ips = [str(node.getInterfaces()[0].getAddress()) for node in nodes[1:]]
                    notifications = ' '.join(f'{address} key "{transfer_id}";' for address in secondary_ips)
                    transfer = (f'    allow-transfer {{ key "{transfer_id}"; }};\n'
                                '    notify explicit;\n'
                                f'    also-notify {{ {notifications} }};')
                primary.setFile(config_path, f'''include "{bind_path}";
include "{transfer_path}";
zone "{zone}" {{
    type master;
    file "{zone_path}";
    update-policy {{
{policy}
    }};
{transfer}
}};
''')
                for secondary in nodes[1:]:
                    secondary.setFile(config_path, f'''include "{transfer_path}";
zone "{zone}" {{
    type slave;
    file "{zone_path}";
    masters {{ {primary_ip} key "{transfer_id}"; }};
    allow-notify {{ key "{transfer_id}"; }};
    allow-transfer {{ none; }};
    allow-update-forwarding {{ none; }};
}};
''')
                primary.setFile(bind_path, publish_key)
                for node in nodes:
                    # Custom includes skip default zone files, so write them explicitly.
                    node.setFile(zone_path, '\n'.join(records) + '\n')
                    options = node.getFile('/etc/bind/named.conf.options')
                    options.setContent(options.get()[1].replace('allow-update { any; };', 'allow-update { none; };'))
                    node.setFile(transfer_path, transfer_key)
                    permissions = ('chown -R root:bind /etc/bind/keys && '
                                   'chmod 750 /etc/bind/keys && chmod 640 /etc/bind/keys/*.key')
                    node.addBuildCommandAtEnd(permissions)
                    node.insertStartCommand(0, permissions)
                authorization._setCredentials(zone, primary_ip, publish_key)

    def render(self, emulator):
        """Render native DNS before update authorizations and hosting configuration."""
        super().render(emulator)
        self.__renderUpdateAuthorizations(emulator)
        registrars, dns_nodes = set(), set()
        for hosting in self._hosting:
            hosting.configure(emulator)
            pair = hosting._nodes[:2]
            if hosting._registrar in registrars or any(id(node) in dns_nodes for node in pair):
                raise ValueError('DNS pairs and registrar hosting configurations must not overlap')
            registrars.add(hosting._registrar)
            dns_nodes.update(id(node) for node in pair)


class DnsHostingServiceMerger(DefaultDomainNameServiceMerger):
    """Merge native DNS while preserving hosting and update authorizations."""

    def _createService(self):
        """Create the subclass for the native merge workflow."""
        return DnsHostingService()

    def doMerge(self, objectA, objectB):
        """Keep authorization objects referenced by publishers such as Registry."""
        merged = super().doMerge(objectA, objectB)
        for service in (objectA, objectB):
            if isinstance(service, DnsHostingService):
                merged._hosting.extend(service._hosting)
                merged._update_authorizations.extend(service._update_authorizations)
        return merged


class _DnsHostingHook(Hook):
    """Append hosting installation after the registrar without a DNS/Registry dependency cycle."""

    def __init__(self, dns):
        self._dns = dns

    def getName(self):
        return 'DnsHosting'

    def getTargetLayer(self):
        return 'FossBillingService'

    def postrender(self, emulator):
        for hosting in self._dns._hosting:
            hosting.install()
