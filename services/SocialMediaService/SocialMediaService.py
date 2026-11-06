"""Install Mastodon, its local database, and an HTTPS reverse proxy."""
import json
from pathlib import Path
import re

from seedemu.core import Server, Service


class SocialMediaServer(Server):
    """Configure one self-contained Mastodon instance."""

    def __init__(self):
        super().__init__()
        self._domain = 'mastodon.com'
        self._port = 443
        self._forwarded_port = None
        self._accounts = []
        self._acme_url = None
        self.appendClassName('SocialMediaService')
        self.setDisplayName('Mastodon')

    def setDomain(self, domain):
        """Set the stable account domain; create its DNS record in the scenario."""
        if (not isinstance(domain, str) or len(domain) > 253 or '.' not in domain
                or any(not re.fullmatch(r'[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?', label)
                       for label in domain.split('.'))):
            raise ValueError('Expected a DNS hostname without a scheme or port')
        self._domain = domain.lower()
        return self

    def setAcmeUrl(self, url):
        """Use an ACME CA trusted by the node for HTTPS certificate issuance."""
        self._acme_url = url
        return self

    def setPort(self, port):
        """Set the canonical HTTPS port, also used inside the simulation."""
        if type(port) is not int or not 1 <= port <= 65535 or port in (80, 3000, 4000):
            raise ValueError('Invalid HTTPS port (80, 3000 and 4000 are reserved)')
        self._port = port
        return self

    def setPortForwarding(self, host_port):
        """Forward HTTPS; use the canonical port to preserve browser URLs."""
        if host_port is not None and (type(host_port) is not int or not 1 <= host_port <= 65535):
            raise ValueError('Expected a TCP port or None')
        self._forwarded_port = host_port
        return self

    def addAccount(self, username, password, *, email, admin=False):
        """Configure a public username, login email and password; synchronize credentials at startup."""
        if not isinstance(username, str) or not re.fullmatch(r'[a-zA-Z0-9_]{1,30}', username):
            raise ValueError('Expected a username of 1-30 letters, digits or underscores')
        if not isinstance(password, str) or not password:
            raise ValueError('Expected a non-empty password')
        if not isinstance(email, str) or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email):
            raise ValueError('Expected a valid login email address')
        if any(account['email'].lower() == email.lower() for account in self._accounts):
            raise ValueError('Email already configured: ' + email)
        if type(admin) is not bool:
            raise ValueError('Expected a boolean admin flag')
        if any(account['username'].lower() == username.lower() for account in self._accounts):
            raise ValueError('Account already configured: ' + username)
        self._accounts.append({'username': username, 'password': password, 'email': email, 'admin': admin})
        return self

    def install(self, node):
        if self._forwarded_port is not None and self._forwarded_port != self._port:
            raise ValueError('Forwarded and canonical HTTPS ports must match; call setPort()')
        files = Path(__file__).parent / 'templates'
        for path in sorted(files.iterdir()):
            if path.is_file():
                node.setFile('/opt/mastodon-service/' + path.name, path.read_text())
        web_domain = self._domain + (f':{self._port}' if self._port != 443 else '')
        node.setFile('/opt/mastodon-service/settings.json', json.dumps({
            'domain': self._domain, 'web_domain': web_domain,
            'port': self._port, 'acme_url': self._acme_url,
        }) + '\n')
        node.setFile('/opt/mastodon-service/accounts.json', json.dumps(self._accounts) + '\n')
        packages = ('ca-certificates curl git build-essential pkg-config '
                         'libssl-dev libyaml-dev libreadline-dev zlib1g-dev libgmp-dev '
                         'libgdbm-dev libffi-dev libicu-dev libidn-dev libpq-dev '
                         'libvips-dev ffmpeg imagemagick postgresql postgresql-contrib '
                         'redis-server nginx openssl supervisor python3 xz-utils')
        if self._acme_url:
            packages += ' certbot cron'
            node.addPersistentStorage('/etc/letsencrypt',
                                      name=f'mastodon-{node.getAsn()}-{node.getName()}-letsencrypt')
        # Install packages in a normal Docker layer for both legacy and BuildKit builds.
        apt_options = '-o Acquire::Retries=3 -o Acquire::http::Timeout=30 -o Acquire::https::Timeout=30 '
        # Keep release names and components; support both sources.list and DEB822.
        node.addBuildCommand(
            'for source in /etc/apt/sources.list /etc/apt/sources.list.d/*.list '
            '/etc/apt/sources.list.d/*.sources; do '
            '[ -f "$source" ] || continue; '
            'sed -i -E '
            "'s@https?://(archive|security).ubuntu.com/ubuntu/?@https://mirrors.tuna.tsinghua.edu.cn/ubuntu/@g; "
            "s@https?://ports.ubuntu.com/ubuntu-ports/?@https://mirrors.tuna.tsinghua.edu.cn/ubuntu-ports/@g' "
            '"$source" || exit 1; done')
        node.addBuildCommand(
            'apt-get ' + apt_options + 'update && '
            'DEBIAN_FRONTEND=noninteractive apt-get ' + apt_options +
            'install -y --no-install-recommends ' + packages)
        # 构建时安装依赖，启动时初始化数据 / Build software, initialize data at startup.
        node.addBuildCommandAtEnd('bash /opt/mastodon-service/install.sh')
        for path in ('/var/lib/postgresql', '/var/lib/redis', '/var/lib/mastodon',
                     '/opt/mastodon/public/system'):
            name = f'mastodon-{node.getAsn()}-{node.getName()}-' + path.rsplit('/', 1)[-1]
            node.addPersistentStorage(path, name=name)
        node.appendStartCommand('bash /opt/mastodon-service/start.sh > /var/log/mastodon-initialize.log 2>&1')
        if self._forwarded_port is not None:
            node.addPortForwarding(self._forwarded_port, self._port)

    def print(self, indent):
        return ' ' * indent + f'Mastodon server: {self._domain}\n'


class SocialMediaService(Service):
    """Install on an ordinary host via install(), Binding, and the Docker compiler."""

    def __init__(self):
        super().__init__()
        self.addDependency('CertificateAuthority', False, True)
        for name in ('Base', 'Routing'):
            self.addDependency(name, False, False)

    def _createServer(self):
        return SocialMediaServer()

    def getName(self):
        return 'SocialMediaService'

    def print(self, indent):
        return ' ' * indent + 'SocialMediaServiceLayer\n'
