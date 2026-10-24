"""Install pinned BIND API and DNS Hosting releases."""
import json
import shlex
from .template import DnsFileTemplates


# Build dependency commands for this service.
APT_CACHE = '--mount=type=cache,id=domainservice-apt,target=/var/cache/apt,sharing=locked '
APT_OPTIONS = '-o Acquire::Retries=3 -o Acquire::http::Timeout=30 -o Acquire::https::Timeout=30 '
APT_PREPARE = ('rm -f /etc/apt/apt.conf.d/docker-clean && '
               'printf \'%s\\n\' \'Binary::apt::APT::Keep-Downloaded-Packages "true";\' '
               '> /etc/apt/apt.conf.d/keep-cache && ')


def apt_install(packages):
    """Update indexes and install in one layer, caching downloads with exclusive access."""
    return (APT_CACHE + APT_PREPARE + 'apt-get ' + APT_OPTIONS + 'update && '
            'DEBIAN_FRONTEND=noninteractive apt-get ' + APT_OPTIONS + 'install -y '
            + ' '.join(shlex.quote(package) for package in packages.split()))


def composer_install(directory):
    """Run Composer with the service PHP 8.5, caching downloads and retaining dependency checks."""
    return ('--mount=type=cache,id=domainservice-composer,target=/var/cache/composer,sharing=locked '
            'cd ' + shlex.quote(directory) + ' && '
            'COMPOSER_CACHE_DIR=/var/cache/composer COMPOSER_ALLOW_SUPERUSER=1 '
            'php8.5 /usr/bin/composer install --no-dev --prefer-dist --no-interaction')

BIND_BUILD_COMMANDS = (
    apt_install('ca-certificates software-properties-common git unzip'),
    'add-apt-repository --no-update -y ppa:ondrej/php',
    apt_install('composer'),
    apt_install('php8.5-cli php8.5-sqlite3 php8.5-swoole php8.5-mbstring '
                'php8.5-xml php8.5-curl php8.5-gmp php8.5-intl'),
    'useradd --system --home /var/lib/bind9-api --shell /usr/sbin/nologin bind9-api',
    'git clone https://github.com/getnamingo/bind9-api.git /opt/bind9-api '
    '&& cd /opt/bind9-api && git checkout f196ca0625b4341f3952d576ea2d223f4b2b6434',
    composer_install('/opt/bind9-api'),
)
DNS_EXTENSION_COMMAND = ('curl --retry 3 --connect-timeout 30 -fsSL '
 'https://github.com/getnamingo/fossbilling-dns/releases/download/v1.2.7/fossbilling-dns-v1.2.7.tar.gz '
 '-o /tmp/fossbilling-dns.tar.gz && echo '
 "'8b6171b985c0bae005550f3c2fac752f9c7ccfb4f3f752d62a6920adc68160de  /tmp/fossbilling-dns.tar.gz' "
 '| sha256sum -c - && tar -xzf /tmp/fossbilling-dns.tar.gz -C /var/www/fossbilling/modules '
 '--strip-components=1 fossbilling-dns-v1.2.7/Servicedns && chown -R www-data:www-data '
 '/var/www/fossbilling/modules/Servicedns && rm /tmp/fossbilling-dns.tar.gz')


def install_nameserver(node, role, address, secondary_ip, registrar_ip, domain):
    """Configure an existing DNS host and prepare its API before BIND starts."""
    for command in BIND_BUILD_COMMANDS:
        node.addBuildCommand(command)
    node.addBuildCommandAtEnd('usermod -aG bind bind9-api')
    node.setFile('/opt/bind9-api/.env', DnsFileTemplates['bind-api.env'].replace('__ADDRESS__', address).replace('__DOMAIN__', domain))
    for name in ('start-bind-api-nameserver.sh', 'init-bind-api-nameserver.php', 'patch-bind-api-nameserver.php'):
        content = DnsFileTemplates[name].replace('__SECONDARY_IP__', secondary_ip).replace('__REGISTRAR_IP__', registrar_ip)
        node.setFile('/opt/dns-hosting/' + name, content)
    node.addBuildCommandAtEnd('php8.5 /opt/dns-hosting/patch-bind-api-nameserver.php')
    node.insertStartCommand(0, 'bash /opt/dns-hosting/start-bind-api-nameserver.sh ' + role)


def install_extension(node, settings):
    """Install the extension; activate and configure its product during setup."""
    node.addBuildCommand(DNS_EXTENSION_COMMAND)
    node.setFile('/opt/dns-hosting/activate-dns-fossbilling.php', DnsFileTemplates['activate-dns-fossbilling.php'])
    node.setFile('/opt/dns-hosting/dns-hosting.json', json.dumps(settings) + '\n')
