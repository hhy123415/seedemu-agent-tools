"""安装固定版本的 BIND API 和 DNS Hosting 扩展。 / Install pinned BIND API and DNS Hosting releases."""
import json
import shlex
from .template import DnsFileTemplates


# 本服务的构建依赖命令。 / Build dependency commands for this service.
APT_CACHE = '--mount=type=cache,id=domainservice-apt,target=/var/cache/apt,sharing=locked '
APT_OPTIONS = '-o Acquire::Retries=3 -o Acquire::http::Timeout=30 -o Acquire::https::Timeout=30 '
APT_PREPARE = ('rm -f /etc/apt/apt.conf.d/docker-clean && '
               'printf \'%s\\n\' \'Binary::apt::APT::Keep-Downloaded-Packages "true";\' '
               '> /etc/apt/apt.conf.d/keep-cache && ')


def apt_install(packages):
    """在同层更新索引并安装包，仅缓存下载文件且串行访问缓存。 / Update indexes and install in one layer, caching downloads with exclusive access."""
    return (APT_CACHE + APT_PREPARE + 'apt-get ' + APT_OPTIONS + 'update && '
            'DEBIAN_FRONTEND=noninteractive apt-get ' + APT_OPTIONS + 'install -y '
            + ' '.join(shlex.quote(package) for package in packages.split()))


def retry(command):
    """最多执行三次，最终失败保留原退出码。 / Attempt at most three times and preserve the final failure status."""
    return ('attempt=0; while true; do ' + command + '; result=$?; '
            '[ "$result" -eq 0 ] && break; attempt=$((attempt + 1)); '
            '[ "$attempt" -lt 3 ] || exit "$result"; sleep 5; done')


PHP_REPOSITORY = retry('add-apt-repository --no-update -y ppa:ondrej/php')


def composer_install(directory):
    """使用服务的 PHP 8.5 执行 Composer，缓存下载并保留依赖检查。 / Run Composer with the service PHP 8.5, caching downloads and retaining dependency checks."""
    return ('--mount=type=cache,id=domainservice-composer,target=/var/cache/composer,sharing=locked '
            'cd ' + shlex.quote(directory) + ' || exit $?; ' + retry(
                'COMPOSER_CACHE_DIR=/var/cache/composer COMPOSER_ALLOW_SUPERUSER=1 '
                'php8.5 /usr/bin/composer install --no-dev --prefer-dist --no-interaction'))

BIND_BUILD_COMMANDS = (
    apt_install('ca-certificates software-properties-common git unzip'),
    PHP_REPOSITORY,
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
    """配置已有 DNS 主机，在 BIND 启动前准备 API。 / Configure an existing DNS host and prepare its API before BIND starts."""
    for command in BIND_BUILD_COMMANDS:
        node.addBuildCommand(command)
    node.addBuildCommandAtEnd('usermod -aG bind bind9-api')
    node.setFile('/opt/bind9-api/.env', DnsFileTemplates['bind-api.env'].replace('__ADDRESS__', address).replace('__DOMAIN__', domain))
    for name in ('start-bind-api-nameserver.sh', 'init-bind-api-nameserver.php', 'patch-bind-api-nameserver.php'):
        content = DnsFileTemplates[name].replace('__SECONDARY_IP__', secondary_ip).replace('__REGISTRAR_IP__', registrar_ip)
        node.setFile('/opt/b02c/' + name, content)
    node.addBuildCommandAtEnd('php8.5 /opt/b02c/patch-bind-api-nameserver.php')
    node.insertStartCommand(0, 'bash /opt/b02c/start-bind-api-nameserver.sh ' + role)


def install_extension(node, settings):
    """安装扩展，setup 阶段再激活并配置产品。 / Install the extension; activate and configure its product during setup."""
    node.addBuildCommand(DNS_EXTENSION_COMMAND)
    node.setFile('/opt/b02c/activate-dns-fossbilling.php', DnsFileTemplates['activate-dns-fossbilling.php'])
    node.setFile('/opt/b02c/dns-hosting.json', json.dumps(settings) + '\n')
