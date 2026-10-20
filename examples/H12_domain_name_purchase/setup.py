#!/usr/bin/env python3
"""等待服务自动初始化，验证运行状态并配置 DNS Hosting 商品。
Wait for automatic service initialization, verify runtime state, and configure DNS Hosting products.
"""
import argparse
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
SERVICES = HERE.parents[1] / 'services' / 'DomainService'
SETUP = SERVICES / 'FossBillingService' / 'setup_fossbilling.py'
PAYMENT_SETUP = SERVICES / 'FakePaymentService' / 'setup_fake_payment.py'
DNS_SETUP = SERVICES / 'DnsHostingService' / 'setup_dns_hosting.py'

# 检查数据库、管理员、EPP 和面板，不输出配置中的凭据。
# Check the database, administrator, EPP, and panel without printing configuration credentials.
REGISTRY_READY = r'''
try {
    $path = '/opt/registry/epp/config.php';
    if (!is_file($path)) { exit(1); }
    $config = require $path;
    $db = new PDO('mysql:host=127.0.0.1;dbname=registry',
        $config['db_username'], $config['db_password'],
        [PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION]);
    foreach (['domain_tld', 'users'] as $table) {
        if ((int)$db->query("SELECT COUNT(*) FROM `$table`")->fetchColumn() < 1) { exit(1); }
    }
    foreach ([(int)$config['epp_port'], 8080] as $port) {
        $socket = @fsockopen('127.0.0.1', $port, $errno, $error, 1);
        if (!$socket) { exit(1); }
        fclose($socket);
    }
    exit(0);
} catch (Throwable $error) { exit(1); }
'''


def run(command, cwd, capture=False, check=True, timeout=None):
    """透传业务命令输出并保留失败退出码；内部探测按需捕获。 / Pass through operation output and exit codes; capture internal probes as needed."""
    return subprocess.run(command, cwd=cwd, text=True, capture_output=capture,
                          check=check, timeout=timeout)


def container_id(output, service):
    """通过 Compose 服务名查找实际容器，避免依赖显示名或 IP。 / Resolve the actual container by Compose service rather than display name or IP."""
    result = run(['docker', 'compose', 'ps', '-q', service], output, capture=True, timeout=30)
    ids = result.stdout.split()
    if len(ids) != 1:
        raise RuntimeError(f'Expected one running container for {service}; check docker compose ps')
    return ids[0]


def require_component(output, container, path):
    """初始化前检查场景组件，避免旧容器被当作完整部署。 / Check scenario components before setup to reject incomplete older deployments."""
    result = run(['docker', 'exec', container, 'test', '-f', path], output,
                 capture=True, check=False, timeout=30)
    if result.returncode:
        raise RuntimeError(f'Missing {path} in container {container}; run domain_name_purchase.py first')


def wait_for_registry(output, container, timeout):
    """有界等待 Registry 自动初始化；不重复执行数据库导入。 / Wait with a deadline for automatic Registry initialization without reimporting its database."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            result = run(['docker', 'exec', container, 'php8.5', '-r', REGISTRY_READY],
                         output, capture=True, check=False, timeout=min(10, max(.1, deadline - time.monotonic())))
            if result.returncode == 0:
                return
        except subprocess.TimeoutExpired:
            pass
        time.sleep(min(2, max(0, deadline - time.monotonic())))
    raise RuntimeError('Registry readiness timed out; inspect Registry container startup logs')


def main(argv=None):
    """检查已启动容器并执行 setup。 / Check running containers and perform setup."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=HERE / 'output')
    parser.add_argument('--registry-service', default='hnode_151_host_1')
    parser.add_argument('--fossbilling-service', default='hnode_150_host_1')
    parser.add_argument('--primary-dns-service', default='hnode_170_host_0')
    parser.add_argument('--secondary-dns-service', default='hnode_170_host_1')
    parser.add_argument('--payment-service', default='hnode_160_host_1')
    parser.add_argument('--dns-product-id', type=int)
    parser.add_argument('--timeout', type=int, default=240, help='Registry 就绪等待秒数 / Registry readiness timeout in seconds')
    args = parser.parse_args(argv)
    if args.dns_product_id is not None and args.dns_product_id <= 0:
        parser.error('--dns-product-id must be positive')
    if args.timeout <= 0:
        parser.error('--timeout must be positive')
    output = args.output.resolve()
    try:
        if not (output / 'docker-compose.yml').is_file():
            raise RuntimeError(f'Missing {output / "docker-compose.yml"}; generate the scenario first')
        registry = container_id(output, args.registry_service)
        registrar = container_id(output, args.fossbilling_service)
        require_component(output, registrar, '/opt/b02c/dns-hosting.json')
        primary = container_id(output, args.primary_dns_service)
        secondary = container_id(output, args.secondary_dns_service)
        require_component(output, registrar, '/opt/b02d/payment-config.json')
        payment = container_id(output, args.payment_service)
        require_component(output, payment, '/opt/b02d/payment-config.json')
        wait_for_registry(output, registry, args.timeout)
        run([sys.executable, str(SETUP), '--container', registrar], output)
        command = [sys.executable, str(DNS_SETUP), '--container', registrar,
                   '--registry-container', registry, '--primary-container', primary,
                   '--secondary-container', secondary]
        if args.dns_product_id is not None:
            command += ['--product-id', str(args.dns_product_id)]
        run(command, output)
        run([sys.executable, str(PAYMENT_SETUP), '--container', registrar,
             '--payment-container', payment], output)
        return 0
    except subprocess.CalledProcessError as error:
        return error.returncode if error.returncode > 0 else 1
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
