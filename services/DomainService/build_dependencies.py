"""生成可缓存且有界重试的依赖安装命令。 / Generate cacheable dependency installation commands with bounded retries."""
import shlex

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
