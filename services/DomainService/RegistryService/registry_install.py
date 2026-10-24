"""实现 Registry 的依赖安装、模板填充、配置文件写入和启动顺序编排，供服务实例调用。

Install dependencies, fill templates, write configuration, and schedule Registry startup operations.
"""
import json
import re
import shlex

from .template import RegistryFileTemplates
from .registry_defaults import (
    NAMINGO_REGISTRY_TLDS, normalize_tlds,
    NAMINGO_REGISTRY_COMMIT, NAMINGO_REGISTRY_DB_PASSWORD,
    NAMINGO_REGISTRY_ADMIN_EMAIL, NAMINGO_REGISTRY_ADMIN_PASSWORD,
)


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

def php_string(value):
    """Escape the contents of a PHP single-quoted string.

    转义 PHP 单引号字符串的内容。
    """
    return value.replace("\\", "\\\\").replace("'", "\\'")


def sql_string(value):
    """Escape a MariaDB string with its default backslash escaping mode.

    按 MariaDB 默认反斜杠转义模式转义字符串。
    """
    return value.replace("\\", "\\\\").replace("'", "''")


def add_startup_operation(host, path, script) -> None:
    """写入完整的运行时操作脚本，并将其加入启动流程。

    Write a complete runtime operation script and append it to the startup sequence.
    """
    host.setFile(path, "#!/bin/bash\n" + script)
    host.appendStartCommand(f"bash {path}")


def install_namingo_registry(host) -> None:
    """安装 Registry 及其本地组件。

    Install Registry and its local dependencies.
    """
    host.addBuildCommand(apt_install('ca-certificates software-properties-common git unzip openssl cron'))
    host.addBuildCommand(PHP_REPOSITORY)
    host.addBuildCommand(apt_install('composer mariadb-server mariadb-client redis-server nginx'))
    host.addBuildCommand(apt_install(
        'php8.5-cli php8.5-fpm php8.5-mysql php8.5-curl php8.5-bcmath php8.5-gmp '
        'php8.5-intl php8.5-mbstring php8.5-xml php8.5-zip php8.5-swoole php8.5-imap '
        'php8.5-gd php8.5-bz2 php8.5-soap php8.5-redis'))
    host.addBuildCommand(
        "git clone https://github.com/getnamingo/registry.git /opt/registry "
        f"&& cd /opt/registry && git checkout {NAMINGO_REGISTRY_COMMIT}"
    )
    for component in ("cp", "epp", "das", "automation"):
        host.addBuildCommand(composer_install(f'/opt/registry/{component}'))


def configure_namingo_registry_database(host, db_password=NAMINGO_REGISTRY_DB_PASSWORD, tlds=NAMINGO_REGISTRY_TLDS) -> None:
    """启动 MariaDB，导入 Registry 数据库结构并初始化所选 TLD。

    Start MariaDB, import the Registry schema, and initialize the selected TLDs.
    """
    tlds = normalize_tlds(tlds)
    tld_values = ", ".join("'." + name + "'" for name in tlds)
    host.setFile("/opt/b02a-registry/database.sql", RegistryFileTemplates['database.sql'] % sql_string(db_password))
    host.setFile("/opt/b02a-registry/initialize-tlds.php", RegistryFileTemplates['initialize-tlds.php'] % (php_string(db_password), tld_values))
    add_startup_operation(host, "/opt/b02a-registry/database.sh", RegistryFileTemplates['database.sh'])


def configure_namingo_registry_cache(host) -> None:
    """启动本地 Redis，供 EPP 查询域名价格。

    Start local Redis for EPP domain pricing queries.
    """
    add_startup_operation(host, "/opt/b02a-registry/cache.sh", (
        '\n'
        'set -e\n'
        'service redis-server start\n'
        'redis-cli ping | grep -qx PONG\n'
    ))


def configure_namingo_registry_admin(host, email=NAMINGO_REGISTRY_ADMIN_EMAIL, password=NAMINGO_REGISTRY_ADMIN_PASSWORD) -> None:
    """创建 Registry 管理面板的管理员账号。

    Create the administrator account for the Registry web panel.
    """
    host.setFile("/opt/b02a-registry/create-admin.php", (
        '<?php\n'
        "putenv('PANEL_EMAIL=%s');\n"
        "putenv('PANEL_PASSWORD=%s');\n"
        "require '/opt/registry/cp/bin/create_admin_user.php';\n"
    ) % (php_string(email), php_string(password)))
    add_startup_operation(host, "/opt/b02a-registry/admin.sh",
                          'php8.5 /opt/b02a-registry/create-admin.php\n')


def configure_namingo_registry_web(host, db_password=NAMINGO_REGISTRY_DB_PASSWORD) -> None:
    """配置并启动 Namingo Registry 网页服务。

    Configure and start the Namingo Registry web panel.
    """
    host.setFile("/opt/b02a-registry/configure-web.php", RegistryFileTemplates['configure-web.php'] % php_string(db_password))
    host.setFile("/etc/nginx/conf.d/registry.conf", RegistryFileTemplates['registry.conf'])
    host.setFile("/etc/php/8.5/fpm/conf.d/99-b02a-registry.ini",
                 (
        'session.cookie_secure=0\n'
        'session.cookie_httponly=1\n'
    ))
    host.addBuildCommandAtEnd(
        "mkdir -p /opt/registry/cp/cache /opt/registry/cp/logs "
        "&& chown -R www-data:www-data /opt/registry/cp/cache /opt/registry/cp/logs"
    )
    add_startup_operation(host, "/opt/b02a-registry/web.sh", RegistryFileTemplates['web.sh'])


def configure_namingo_registry_component(host, component, settings, db_password=NAMINGO_REGISTRY_DB_PASSWORD) -> str:
    """写入组件配置脚本，并返回执行该脚本的命令。

    Write a component configuration script and return its execution command.
    """
    name = component.replace("/", "-")
    host.setFile(f"/opt/b02a-registry/configure-{name}.php", RegistryFileTemplates['configure-component.php'] % (component, php_string(db_password), settings, component))
    return f"php8.5 /opt/b02a-registry/configure-{name}.php\n"


def configure_namingo_registry_epp(host, epp_port=700, db_password=NAMINGO_REGISTRY_DB_PASSWORD) -> None:
    """配置 EPP 及其 TLS 服务端证书，然后启动服务。

    此证书用于 EPP 连接，与 Registry 网页服务的证书独立。
    自签名证书仅用于仿真测试；启用证书认证时，应使用可信 CA，
    并在 Registrar 客户端验证服务端证书。若要通过客户端证书识别
    Registrar，还需在 Registry 中配置双向 TLS 验证。

    Configure EPP and its TLS server certificate, then start the service.

    This certificate is independent of the web panel certificate.
    The self-signed certificate is for simulation only. Certificate authentication
    requires a trusted CA and server certificate verification by the registrar.
    Identifying registrars by client certificate also requires mutual TLS in Registry.
    """
    configure = configure_namingo_registry_component(host, "epp", (
        '\n'
        "    'epp_host' => '0.0.0.0',\n"
        "    'epp_port' => %d,\n"
        "    'epp_pid' => '/var/run/epp.pid',\n"
        "    'epp_prefix' => 'com',\n"
        "    'test_tlds' => '',\n"
    ) % epp_port, db_password)
    host.addBuildCommandAtEnd(
        "openssl req -x509 -newkey rsa:2048 -nodes -days 3650 "
        "-subj /CN=b02a-com-registry "
        "-keyout /opt/registry/epp/epp.key -out /opt/registry/epp/epp.crt "
        "&& chmod 600 /opt/registry/epp/epp.key"
    )
    add_startup_operation(host, "/opt/b02a-registry/epp.sh", configure + (
        '\n'
        'cd /opt/registry/epp\n'
        'php8.5 start_epp.php >> /var/log/namingo/epp-start.log 2>&1 &\n'
    ))


def configure_namingo_registry_das(host, db_password=NAMINGO_REGISTRY_DB_PASSWORD) -> None:
    """配置并启动 IPv4 域名可用性查询服务。

    Configure and start the IPv4 domain availability service.
    """
    configure = configure_namingo_registry_component(host, "das", "    'das_ipv6' => false,\n", db_password)
    add_startup_operation(host, "/opt/b02a-registry/das.sh", configure + (
        '\n'
        'cd /opt/registry/das\n'
        'php8.5 start_das.php >> /var/log/namingo/das-start.log 2>&1 &\n'
    ))


def configure_namingo_registry_lifecycle(host, db_password=NAMINGO_REGISTRY_DB_PASSWORD) -> None:
    """配置 automation 组件，并通过 cron 每 5 分钟执行域名生命周期维护脚本。

    DNS 委派发布由 configure_dns_publication 配置的独立发布循环负责。

    Configure automation and run domain lifecycle maintenance every five minutes via cron.

    The separate loop configured by configure_dns_publication handles DNS delegation publication.
    """
    configure = configure_namingo_registry_component(host, "automation", "", db_password)
    host.setFile("/etc/cron.d/namingo-lifecycle",
                 '*/5 * * * * root cd /opt/registry/automation && php8.5 domain-lifecycle-manager.php >> /var/log/namingo/lifecycle-start.log 2>&1\n')
    add_startup_operation(host, "/opt/b02a-registry/lifecycle.sh",
                          configure + 'service cron start\n')


def configure_epp_registrar(host, db_password, username, password, prefix, source_ip, domains):
    """生成账号初始化脚本，在 EPP 读取白名单前运行。 / Generate account initialization to run before EPP reads its whitelist."""
    values = {
        '__REGISTRY_DB_PASSWORD__': db_password, '__EPP_USERNAME__': username,
        '__EPP_PASSWORD__': password, '__EPP_PREFIX__': prefix,
        '__EPP_SOURCE_IP__': source_ip, '__RESERVED_DOMAINS__': json.dumps(domains),
    }
    # 单次替换，防止凭据内的占位符被再次展开。 / Replace once to avoid expanding markers inside credentials.
    script = re.sub(r'__[A-Z_]+__', lambda match: php_string(values[match.group()]),
                    RegistryFileTemplates['create-epp-registrar.php'])
    path = f'/opt/b02a-registry/create-registrar-{username}.php'
    host.setFile(path, script)
    host.addBuildCommandAtEnd(f'chmod 600 {path}')
    host.appendStartCommand(f'chmod 600 {path} && php8.5 {path}')


def configure_dns_publication(host, tlds, interval):
    """安装发布脚本和定时循环，不在脚本中复制数据库凭据。 / Install publication and its loop without copying database credentials into scripts."""
    host.addSoftware('bind9-dnsutils')
    host.setFile('/opt/b02a-registry/publish-registry.php', RegistryFileTemplates['publish-registry.php'])
    commands = '\n'.join(
        f'    timeout 25 php8.5 /opt/b02a-registry/publish-registry.php {tld} >> /var/log/namingo/dns-publication.log 2>&1'
        for tld in tlds)
    host.setFile('/opt/b02a-registry/publish-loop.sh',
                 '#!/bin/bash\n# 各 TLD 失败独立记录并重试。 / Log failures independently and retry each TLD.\n'
                 'while true; do\n' + commands + f'\n    sleep {interval}\ndone\n')
    host.appendStartCommand('bash /opt/b02a-registry/publish-loop.sh &')
