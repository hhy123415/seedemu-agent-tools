"""将 FOSSBilling 注册商安装到已有主机。 / Install the FOSSBilling registrar on an existing host."""
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit

from seedemu.core import Server, Service
from ..RegistryService import RegistryServer
from ..RegistryService.registry_defaults import normalize_tlds
from . import fossbilling_defaults as defaults
from .fossbilling_install import install_fossbilling, configure_fossbilling


def credential(value, name):
    """拒绝空值、换行和空字符。 / Reject empty values, newlines, and NUL characters."""
    if not isinstance(value, str) or not value or any(c in value for c in '\x00\r\n'):
        raise ValueError(f'{name} must be a non-empty single-line string')
    return value


class FossBillingServer(Server):
    """管理注册商实例参数和 Registry 连接。 / Manage registrar instance settings and its Registry connection."""

    def __init__(self):
        """设置注册商仿真默认值，不固定主机地址。 / Set registrar simulation defaults without fixed host addresses."""
        super().__init__()
        self._forwarded_port = 18080
        self._registry = 'registry'
        self._username = defaults.EPP_USERNAME
        self._password = defaults.EPP_PASSWORD
        self._prefix = defaults.EPP_PREFIX
        self._tlds = None
        self._prices = {}
        self._reserved = []
        self._connection = None
        self._settings = {
            'database_password': defaults.DATABASE_PASSWORD,
            'admin_email': defaults.ADMIN_EMAIL, 'admin_password': defaults.ADMIN_PASSWORD,
            'client_email': defaults.CLIENT_EMAIL, 'client_password': defaults.CLIENT_PASSWORD,
            'client_profile': dict(defaults.CLIENT_PROFILE),
            'browser_hosts': ['localhost:18080', '127.0.0.1:18080'],
        }
        self.appendClassName('FossBillingService')
        self.setDisplayName('FOSSBilling Registrar')

    def setPortForwarding(self, host_port):
        """设置 Web 宿主机端口，None 禁用映射。 / Set the host Web port; None disables forwarding."""
        if host_port is not None and (type(host_port) is not int or not 1 <= host_port <= 65535):
            raise ValueError('Host port must be an integer between 1 and 65535, or None')
        self._forwarded_port = host_port
        return self

    def setRegistry(self, virtual_node, username=defaults.EPP_USERNAME, password=defaults.EPP_PASSWORD, prefix=defaults.EPP_PREFIX):
        """指定 Registry 虚拟节点和专用 EPP 账号。 / Select a Registry virtual node and dedicated EPP account."""
        values = [credential(value, name) for value, name in
                  [(virtual_node, 'Registry node'), (username, 'EPP username'), (password, 'EPP password'), (prefix, 'EPP prefix')]]
        self._registry, self._username, self._password, self._prefix = values
        return self

    def setDatabasePassword(self, password):
        """设置首次创建数据库账号的密码。 / Set the initial database account password."""
        self._settings['database_password'] = credential(password, 'Database password')
        return self

    def setAdminAccount(self, email, password):
        """设置首次安装的管理员凭据。 / Set initial administrator credentials."""
        email, password = credential(email, 'Admin email'), credential(password, 'Admin password')
        self._settings.update(admin_email=email, admin_password=password)
        return self

    def setClientAccount(self, email, password, profile=None):
        """配置演示客户，可覆盖默认 EPP 联系资料。 / Configure the demo client with optional EPP contact overrides."""
        email, password = credential(email, 'Client email'), credential(password, 'Client password')
        values = dict(self._settings['client_profile'])
        if profile is not None:
            if not isinstance(profile, dict) or set(profile) - set(defaults.CLIENT_PROFILE):
                raise ValueError('Unsupported client contact fields')
            values.update({key: credential(value, key) for key, value in profile.items()})
        self._settings.update(client_email=email, client_password=password, client_profile=values)
        return self

    def setTlds(self, tlds):
        """选择销售的 TLD，默认继承 Registry 管理范围。 / Select offered TLDs; inherit Registry TLDs by default."""
        self._tlds = normalize_tlds(tlds)
        return self

    def setTldPrice(self, tld, registration='11.99', renewal='11.99', transfer='11.99'):
        """设置新建 TLD 的价格，不覆盖数据库已有价格。 / Set prices for new TLDs without overwriting existing database prices."""
        name = normalize_tlds([tld])[0]
        prices = []
        for value in (registration, renewal, transfer):
            try:
                price = Decimal(str(value))
                if not price.is_finite() or price < 0 or price > Decimal('999999.99') or price != price.quantize(Decimal('.01')):
                    raise ValueError('Prices must be non-negative amounts with at most two decimal places')
            except InvalidOperation as exc:
                raise ValueError('Invalid TLD price') from exc
            prices.append(format(price, '.2f'))
        self._prices[name] = prices
        return self

    def setBrowserHosts(self, hosts):
        """设置允许覆盖内部 URL 的浏览器 Host；端口映射另用 setPortForwarding() 配置。 / Set allowed browser Hosts; configure forwarding separately with setPortForwarding()."""
        if not isinstance(hosts, (list, tuple)):
            raise ValueError('Browser hosts must be a list or tuple')
        result = []
        for host in hosts:
            credential(host, 'Browser host')
            parsed = urlsplit('http://' + host)
            if (not parsed.hostname or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment
                    or any(c.isspace() for c in host) or '\\' in host or parsed.port == 0):
                raise ValueError('Browser hosts must be host[:port] values')
            result.append(host.lower())
        self._settings['browser_hosts'] = list(dict.fromkeys(result))
        return self

    def setReservedDomains(self, domains):
        """指定由该注册商预先占用的域名，渲染时校验 TLD。 / Reserve domains for this registrar, validating TLDs during rendering."""
        if not isinstance(domains, (list, tuple)):
            raise ValueError('Reserved domains must be a list or tuple')
        self._reserved = list(domains)
        return self

    def getEppUsername(self):
        """返回 EPP 注册商标识，不暴露密码。 / Return the EPP registrar identifier without exposing its password."""
        return self._username

    def getReservedDomains(self):
        """返回预置域名副本。 / Return a copy of reserved domain names."""
        return list(self._reserved)

    def configure(self, emulator, host):
        """解析绑定地址，并在 Registry 注册账号初始化任务。 / Resolve bound addresses and register account initialization with Registry."""
        registry = emulator.getServerByVirtualNodeName(self._registry)
        if not isinstance(registry, RegistryServer):
            raise ValueError('The selected virtual node must use RegistryService')
        registry_host = emulator.getBindingFor(self._registry)
        if registry_host is host:
            raise ValueError('FOSSBilling and Registry require separate hosts')
        tlds = list(self._tlds) if self._tlds is not None else registry.getTlds()
        if set(tlds) - set(registry.getTlds()) or set(self._prices) - set(tlds):
            raise ValueError('Offered TLDs must be managed by Registry, and prices must refer to offered TLDs')
        address = str(host.getInterfaces()[0].getAddress())
        registry.addEppRegistrar(self._username, self._password, self._prefix, address, self._reserved)
        self._connection = {
            'host': str(registry_host.getInterfaces()[0].getAddress()), 'port': registry.getEppPort(),
            'clid': self._username, 'pw': self._password, 'registrarprefix': self._prefix,
            'local_cert': '/var/www/fossbilling/ssl/namingo_cert.pem',
            'local_pk': '/var/www/fossbilling/ssl/namingo_key.pem',
        }
        self._settings['url'] = f'http://{address}:8080/'
        self._settings['prices'] = {'.' + name: list(self._prices.get(name, ['11.99'] * 3)) for name in tlds}

    def install(self, node):
        """生成安装和启动操作，在容器内自动初始化应用。 / Generate installation and startup operations that initialize the application inside the container."""
        if self._connection is None:
            raise RuntimeError('Configure the service through emulator.render() before installing')
        install_fossbilling(node)
        configure_fossbilling(node, self._settings, self._connection)
        if self._forwarded_port is not None:
            node.addPortForwarding(self._forwarded_port, 8080)

    def print(self, indent):
        """返回实例描述。 / Return the server description."""
        return ' ' * indent + 'FOSSBilling registrar server\n'


class FossBillingService(Service):
    """依赖 Registry 的注册商服务层。 / Registrar service layer depending on Registry."""

    def __init__(self):
        """声明基础层和 Registry 依赖。 / Declare base layer and Registry dependencies."""
        super().__init__()
        for name in ('Base', 'Routing', 'RegistryService'):
            self.addDependency(name, False, False)

    def configure(self, emulator):
        """先解析实例关联，再使用标准服务绑定流程。 / Resolve instance links before standard service binding."""
        for vnode, server in self._pending_targets.items():
            server.configure(emulator, emulator.getBindingFor(vnode))
        super().configure(emulator)

    def _createServer(self):
        """创建注册商实例。 / Create a registrar instance."""
        return FossBillingServer()

    def getName(self):
        """返回服务层名称。 / Return the service layer name."""
        return 'FossBillingService'

    def getConflicts(self):
        """禁止与 Registry 在同一主机争用 Web 和数据库配置。 / Prevent sharing Registry's web and database configuration on the same host."""
        return ['RegistryService']

    def print(self, indent):
        """返回服务层描述。 / Return the layer description."""
        return ' ' * indent + 'FossBillingServiceLayer\n'
