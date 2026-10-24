"""Install FOSSBilling and write local runtime settings."""
import json
import shlex
from .template import FossBillingFileTemplates
from .fossbilling_defaults import FOSSBILLING_VERSION, NAMINGO_EPP_INSTALLER_COMMIT
from ..RegistryService.registry_install import sql_string


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


def install_fossbilling(host) -> None:
    """Install the release and Namingo EPP adapter."""
    host.setFile("/opt/fossbilling/patch-cart-checkout-fossbilling.php",
                 FossBillingFileTemplates['patch_cart_checkout_fossbilling.php'])
    host.addBuildCommandAtEnd("php8.5 /opt/fossbilling/patch-cart-checkout-fossbilling.php "
                              "&& php8.5 -l /var/www/fossbilling/modules/Cart/Service.php")
    host.addBuildCommand(apt_install('ca-certificates curl software-properties-common unzip openssl cron python3'))
    host.addBuildCommand('add-apt-repository --no-update -y ppa:ondrej/php')
    host.addBuildCommand(apt_install('mariadb-server mariadb-client nginx'))
    host.addBuildCommand(apt_install(
        'php8.5-cli php8.5-fpm php8.5-mysql php8.5-curl php8.5-gd php8.5-intl '
        'php8.5-mbstring php8.5-xml php8.5-zip php8.5-bcmath php8.5-gmp php8.5-imap'))
    host.addBuildCommand(
        "mkdir -p /var/www/fossbilling "
        "&& curl --retry 3 --connect-timeout 30 -fsSL https://github.com/FOSSBilling/FOSSBilling/releases/download/"
        f"{FOSSBILLING_VERSION}/FOSSBilling-{FOSSBILLING_VERSION}.zip "
        "-o /tmp/fossbilling.zip "
        "&& unzip -q /tmp/fossbilling.zip -d /var/www/fossbilling "
        "&& chown -R www-data:www-data /var/www/fossbilling"
    )
    # The official installer generates the Namingo adapter and checks the release hash.
    host.addBuildCommand(
        "curl --retry 3 --connect-timeout 30 -fsSL https://raw.githubusercontent.com/getnamingo/"
        f"fossbilling-epp-registrar/{NAMINGO_EPP_INSTALLER_COMMIT}/"
        "install-fossbilling-epp.sh "
        "-o /tmp/install-fossbilling-epp.sh "
        "&& bash /tmp/install-fossbilling-epp.sh namingo /var/www/fossbilling"
    )


def configure_fossbilling(host, settings, connection):
    """Schedule database and web startup and save setup parameters."""
    host.setFile('/opt/fossbilling/database.sql',
                 "CREATE USER IF NOT EXISTS 'fossbilling'@'localhost' IDENTIFIED BY '"
                 + sql_string(settings['database_password']) + "';\n"
                 "GRANT ALL PRIVILEGES ON fossbilling.* TO 'fossbilling'@'localhost';\n")
    for name in ('database.sh', 'web.sh'):
        host.setFile('/opt/fossbilling/' + name, FossBillingFileTemplates[name])
        host.appendStartCommand('sh /opt/fossbilling/' + name)
    host.setFile('/etc/nginx/conf.d/fossbilling.conf', FossBillingFileTemplates['fossbilling.conf'])
    for name, value in [('setup-config.json', settings), ('epp-connection.json', connection)]:
        path = '/opt/fossbilling/' + name
        host.setFile(path, json.dumps(value) + '\n')
        host.addBuildCommandAtEnd('chmod 600 ' + path)
        host.insertStartCommand(0, 'chmod 600 ' + path)

    # Initialize locally after web startup, without waiting for other services.
    for name in ('initialize-fossbilling.py', 'configure-site-url.php', 'configure-epp.php', 'create-client.php'):
        host.setFile('/opt/fossbilling/' + name, FossBillingFileTemplates[name])
    host.appendStartCommand('python3 /opt/fossbilling/initialize-fossbilling.py > /var/log/fossbilling-initialize.log 2>&1')
