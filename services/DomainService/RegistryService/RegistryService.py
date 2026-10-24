"""定义 Registry 服务层和服务实例，管理实例参数，并在渲染阶段将服务安装到绑定的已有主机。

Define the Registry layer and server, and install each instance on its bound existing host during rendering.
"""
import ipaddress
import json
import re

from seedemu.core import Node, Server, Service
from . import registry_install as installer
from .registry_defaults import NAMINGO_REGISTRY_TLDS, normalize_tlds


class RegistryServer(Server):
    """Registry 服务实例，包含数据库、缓存、面板、EPP、DAS 和生命周期定时任务。

    默认管理 .com/.net 仿真 TLD。
    Registry, MariaDB, Redis, web panel, EPP, DAS and lifecycle cron.

    Defaults manage the simulated .com/.net TLDs.
    """

    def __init__(self):
        """使用默认仿真参数初始化独立服务实例。 / Initialize an instance with simulation defaults."""
        super().__init__()
        self._forwarded_port = 18081
        self._dns_authorizations = {}
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
        """设置 Web 宿主机端口，None 禁用映射。 / Set the host Web port; None disables forwarding."""
        if host_port is not None and (type(host_port) is not int or not 1 <= host_port <= 65535):
            raise ValueError('Host port must be an integer between 1 and 65535, or None')
        self._forwarded_port = host_port
        return self

    @staticmethod
    def _validateCredential(value, name):
        """拒绝空值和含换行或空字符的凭据。 / Reject empty credentials and embedded newline or NUL characters."""
        if not isinstance(value, str) or not value or any(c in value for c in "\x00\r\n"):
            raise ValueError(f'{name} must be a non-empty single-line string')

    def setAdminAccount(self, email: str, password: str):
        """设置首次初始化管理员的凭据，并返回当前实例。 / Set initial administrator credentials and return this instance."""
        self._validateCredential(email, 'Admin email')
        self._validateCredential(password, 'Admin password')
        self._admin_email = email
        self._admin_password = password
        return self

    def setDatabasePassword(self, password: str):
        """设置首次创建数据库账号的密码，并返回当前实例。 / Set the initial database account password and return this instance."""
        self._validateCredential(password, 'Database password')
        self._db_password = password
        return self

    def setTlds(self, tlds):
        """设置首次初始化的 TLD，返回当前实例；不迁移已有数据库。 / Set initial TLDs and return this instance; existing databases are not migrated."""
        self._tlds = normalize_tlds(tlds)
        return self

    def getTlds(self):
        """返回 TLD 列表副本，不包含前导点。 / Return a copy of the TLD list without leading dots."""
        return list(self._tlds)

    def setEppPort(self, port: int):
        """校验并设置 EPP 监听端口，返回当前实例。 / Validate and set the EPP listening port, returning this instance."""
        if not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535:
            raise ValueError('EPP port must be between 1 and 65535')
        self._epp_port = port
        return self

    def setDnsAuthorization(self, tld, address, key):
        """保存 DNS 服务提供的发布目标及 TSIG 密钥。 / Store the publication target and TSIG key supplied by DNS."""
        tld = normalize_tlds([tld])[0]
        if tld not in self._tlds:
            raise ValueError('DNS authorization TLD must be managed by Registry')
        address = str(ipaddress.IPv4Address(address))
        if not isinstance(key, str) or not key.strip():
            raise ValueError('DNS authorization requires a TSIG key')
        self._dns_authorizations[tld] = (address, key)
        return self

    def _installDnsAuthorization(self, node):
        """将授权写入实际绑定主机。 / Write authorization files to the actual bound host."""
        if set(self._dns_authorizations) - set(self._tlds):
            raise ValueError('Authorized TLDs must remain managed by Registry')
        publications = {}
        for tld, (address, key) in self._dns_authorizations.items():
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
        """为指定 TLD 启用周期委派发布，需先配置 DNS 授权。 / Enable periodic delegation publication for TLDs with DNS authorization configured."""
        values = normalize_tlds(tlds)
        if set(values) - set(self._tlds):
            raise ValueError('Publication TLDs must be managed by Registry')
        if not isinstance(interval, int) or isinstance(interval, bool) or interval < 1:
            raise ValueError('Publication interval must be a positive integer')
        self._publication_tlds = values
        self._publication_interval = interval
        return self

    def getEppPort(self):
        """读取 EPP 端口供依赖服务对接。 / Return the EPP port for dependent services."""
        return self._epp_port

    def addEppRegistrar(self, username, password, prefix, source_ip, reserved_domains=()):
        """在 EPP 启动前初始化专用账号、白名单和预置域名。 / Initialize an account, whitelist, and reserved domains before EPP starts."""
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
        """按数据库、缓存及应用依赖顺序配置绑定主机。 / Configure the bound host in database, cache, and application dependency order."""
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
        """返回指定缩进的实例描述。 / Return the server description at the requested indentation."""
        return ' ' * indent + 'Namingo Registry server\n'


class RegistryService(Service):
    """将 Registry 实例安装到已有主机的服务层。 / Service layer that installs Registry instances on existing hosts."""

    def __init__(self):
        """声明基础网络和路由层依赖。 / Declare base network and routing dependencies."""
        super().__init__()
        self.addDependency('Base', False, False)
        self.addDependency('Routing', False, False)
        self.addDependency('DomainNameService', False, True)

    def _createServer(self):
        """创建供虚拟节点绑定使用的服务实例。 / Create a server instance for virtual node binding."""
        return RegistryServer()

    def getName(self):
        """返回服务层注册名称。 / Return the service layer registration name."""
        return 'RegistryService'

    def print(self, indent: int):
        """返回指定缩进的服务层描述。 / Return the layer description at the requested indentation."""
        return ' ' * indent + 'RegistryServiceLayer\n'
