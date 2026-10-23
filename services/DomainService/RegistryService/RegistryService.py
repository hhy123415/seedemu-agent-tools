"""Define the Registry layer and server, and install each instance on its bound existing host during rendering.
"""
import ipaddress
import json
import re

from seedemu.core import Node, Server, Service
from . import registry_install as installer
from .registry_defaults import NAMINGO_REGISTRY_TLDS, normalize_tlds


class RegistryServer(Server):
    """    Registry, MariaDB, Redis, web panel, EPP, DAS and lifecycle cron.

    Defaults manage the simulated .com/.net TLDs.
    """

    def __init__(self):
        """Initialize an instance with simulation defaults."""
        super().__init__()
        self._forwarded_port = 18081
        self._dns_authorization = None
        self._publication_tlds = ()
        self._publication_interval = 30
        self._registrars = {}
        self._tlds = NAMINGO_REGISTRY_TLDS
        self._epp_port = 700
        self._db_password = installer.NAMINGO_REGISTRY_DB_PASSWORD
        self._admin_email = installer.NAMINGO_REGISTRY_ADMIN_EMAIL
        self._admin_password = installer.NAMINGO_REGISTRY_ADMIN_PASSWORD
        self.appendClassName('RegistryService')
        self.setDisplayName('Namingo COM Registry')

    def setPortForwarding(self, host_port):
        """Set the host Web port; None disables forwarding."""
        if host_port is not None and (type(host_port) is not int or not 1 <= host_port <= 65535):
            raise ValueError('Host port must be an integer between 1 and 65535, or None')
        self._forwarded_port = host_port
        return self

    @staticmethod
    def _validateCredential(value, name):
        """Reject empty credentials and embedded newline or NUL characters."""
        if not isinstance(value, str) or not value or any(c in value for c in "\x00\r\n"):
            raise ValueError(f'{name} must be a non-empty single-line string')

    def setAdminAccount(self, email: str, password: str):
        """Set initial administrator credentials and return this instance."""
        self._validateCredential(email, 'Admin email')
        self._validateCredential(password, 'Admin password')
        self._admin_email = email
        self._admin_password = password
        return self

    def setDatabasePassword(self, password: str):
        """Set the initial database account password and return this instance."""
        self._validateCredential(password, 'Database password')
        self._db_password = password
        return self

    def setTlds(self, tlds):
        """Set initial TLDs and return this instance; existing databases are not migrated."""
        self._tlds = normalize_tlds(tlds)
        return self

    def getTlds(self):
        """Return a copy of the TLD list without leading dots."""
        return list(self._tlds)

    def setEppPort(self, port: int):
        """Validate and set the EPP listening port, returning this instance."""
        if not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535:
            raise ValueError('EPP port must be between 1 and 65535')
        self._epp_port = port
        return self

    def setDnsAuthorization(self, authorization):
        """Accept DNS authorization and validate Registry-owned TLDs."""
        if {zone.rstrip('.') for zone in authorization.getZones()} - set(self._tlds):
            raise ValueError('DNS authorization zones must be managed by Registry')
        self._dns_authorization = authorization
        return self

    def _installDnsAuthorization(self, node):
        """Read resolved DNS credentials and write them to the bound host."""
        if self._dns_authorization is None:
            return
        zones = self._dns_authorization.getZones()
        if {zone.rstrip('.') for zone in zones} - set(self._tlds):
            raise ValueError('Authorized TLDs must remain managed by Registry')
        # Read all credentials before writing files.
        credentials = {zone.rstrip('.'): self._dns_authorization.getCredentials(zone) for zone in zones}
        publications = {}
        for tld, (address, key) in credentials.items():
            path = f'/opt/registry/dns-keys/{tld}-publisher.key'
            node.setFile(path, key)
            entry = {'zone': tld + '.', 'server': address, 'key_file': path}
            publications[tld + '.'] = entry
            node.setFile(f'/opt/registry/dns-publication-{tld}.json', json.dumps(entry) + '\n')
            permissions = f'chmod 700 /opt/registry/dns-keys && chmod 600 {path}'
            node.addBuildCommandAtEnd(permissions)
            node.insertStartCommand(0, permissions)
        if publications:
            node.setFile('/opt/registry/dns-publications.json', json.dumps(publications) + '\n')

    def enableDnsPublication(self, tlds, interval=30):
        """Enable periodic delegation publication for TLDs with DNS authorization configured."""
        values = normalize_tlds(tlds)
        if set(values) - set(self._tlds):
            raise ValueError('Publication TLDs must be managed by Registry')
        if not isinstance(interval, int) or isinstance(interval, bool) or interval < 1:
            raise ValueError('Publication interval must be a positive integer')
        self._publication_tlds = values
        self._publication_interval = interval
        return self

    def getEppPort(self):
        """Return the EPP port for dependent services."""
        return self._epp_port

    def addEppRegistrar(self, username, password, prefix, source_ip, reserved_domains=()):
        """Initialize an account, whitelist, and reserved domains before EPP starts."""
        self._validateCredential(password, 'EPP password')
        if not isinstance(username, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,32}', username):
            raise ValueError('EPP username must contain 1-32 ASCII letters, digits, underscores or hyphens')
        if not isinstance(prefix, str) or not re.fullmatch(r'[A-Z0-9]{1,5}', prefix):
            raise ValueError('EPP prefix must contain 1-5 uppercase ASCII letters or digits')
        source_ip = str(ipaddress.IPv4Address(source_ip))
        if username in self._registrars or any(item['prefix'] == prefix for item in self._registrars.values()):
            raise ValueError('Duplicate EPP registrar username or prefix')
        domains = []
        if not isinstance(reserved_domains, (list, tuple)):
            raise ValueError('Reserved domains must be a list or tuple')
        for name in reserved_domains:
            if not isinstance(name, str):
                raise ValueError('Reserved domain names must be strings')
            name = name.lower()
            if (not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.[a-z0-9-]+', name)
                    or name.rsplit('.', 1)[-1] not in self._tlds):
                raise ValueError('Reserved domains must be second-level names under a managed TLD')
            if name not in domains:
                domains.append(name)
        self._registrars[username] = dict(password=password, prefix=prefix, source_ip=source_ip, domains=domains)
        return self

    def install(self, node: Node):
        """Configure the bound host in database, cache, and application dependency order."""
        self._installDnsAuthorization(node)
        if self._publication_tlds:
            files = {file.get()[0] for file in node.getFiles()}
            for tld in self._publication_tlds:
                if f'/opt/registry/dns-publication-{tld}.json' not in files:
                    raise ValueError(f'Configure Registry DNS authorization for {tld} before enabling publication')
        installer.install_namingo_registry(node)
        installer.configure_namingo_registry_database(node, self._db_password, self._tlds)
        for username, account in self._registrars.items():
            installer.configure_epp_registrar(node, self._db_password, username, **account)
        installer.configure_namingo_registry_cache(node)
        installer.configure_namingo_registry_web(node, self._db_password)
        if self._forwarded_port is not None:
            node.addPortForwarding(self._forwarded_port, 8080)
        installer.configure_namingo_registry_admin(node, self._admin_email, self._admin_password)
        installer.configure_namingo_registry_epp(node, self._epp_port, self._db_password)
        installer.configure_namingo_registry_das(node, self._db_password)
        installer.configure_namingo_registry_lifecycle(node, self._db_password)
        if self._publication_tlds:
            if set(self._publication_tlds) - set(self._tlds):
                raise ValueError('Publication TLDs must remain managed by Registry')
            installer.configure_dns_publication(node, self._publication_tlds, self._publication_interval)

    def print(self, indent: int):
        """Return the server description at the requested indentation."""
        return ' ' * indent + 'Namingo Registry server\n'


class RegistryService(Service):
    """Service layer that installs Registry instances on existing hosts."""

    def __init__(self):
        """Declare base network and routing dependencies."""
        super().__init__()
        self.addDependency('Base', False, False)
        self.addDependency('Routing', False, False)
        self.addDependency('DomainNameService', False, True)

    def _createServer(self):
        """Create a server instance for virtual node binding."""
        return RegistryServer()

    def getName(self):
        """Return the service layer registration name."""
        return 'RegistryService'

    def print(self, indent: int):
        """Return the layer description at the requested indentation."""
        return ' ' * indent + 'RegistryServiceLayer\n'
