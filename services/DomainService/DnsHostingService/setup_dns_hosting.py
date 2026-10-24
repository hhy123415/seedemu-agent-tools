#!/usr/bin/env python3
"""核对托管 NS host 并配置 DNS Hosting 产品，不修改客户订单。 / Verify hosted NS objects and configure the DNS Hosting product without modifying customer orders."""
import argparse
import ipaddress
import json
import subprocess
import sys
import time

if __package__:
    from .template import DnsFileTemplates
else:
    from template import DnsFileTemplates


def docker(container, *command, input_text=None, check=True):
    """捕获容器输出，凭据只在内存和标准输入中传递。 / Capture container output and pass credentials only in memory and stdin."""
    return subprocess.run(['docker', 'exec', *(['-i'] if input_text is not None else []), container, *command],
                          input=input_text, text=True, capture_output=True, check=check, timeout=180)


def read_credentials(container, role):
    """等待 API 本机凭据生成，不打印账号密码。 / Wait for local API credentials without printing them."""
    for attempt in range(60):
        result = docker(container, 'cat', '/opt/b02c/bind-api-credentials.json', check=False)
        if result.returncode == 0:
            value = json.loads(result.stdout)
            if not all(isinstance(value.get(key), str) and value[key] for key in ('username', 'password')):
                raise RuntimeError(f'{role}: invalid BIND API credentials')
            return value
        if attempt < 59:
            time.sleep(2)
    raise RuntimeError(f'{role}: BIND API credentials are not ready')


def wait_for_api(container, address):
    """从注册商容器确认 API 端口可达，认证由产品配置脚本验证。 / Check API reachability from the registrar; product setup verifies authentication."""
    address = str(ipaddress.IPv4Address(address))
    code = f'$s=@fsockopen("{address}",7650,$e,$m,1); if(!$s)exit(1); fclose($s);'
    for attempt in range(60):
        if docker(container, 'php8.5', '-r', code, check=False).returncode == 0:
            return
        if attempt < 59:
            time.sleep(2)
    raise RuntimeError(f'BIND API at {address}:7650 did not become reachable')


def main(argv=None):
    """依次核对 host、验证主从 API 并配置产品。 / Check hosts, verify both APIs, and configure the product."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--container', required=True)
    parser.add_argument('--registry-container', required=True)
    parser.add_argument('--primary-container', required=True)
    parser.add_argument('--secondary-container', required=True)
    parser.add_argument('--product-id', type=int)
    args = parser.parse_args(argv)
    if args.product_id is not None and args.product_id <= 0:
        parser.error('--product-id must be positive')
    stage = 'read configuration'
    try:
        hosting = json.loads(docker(args.container, 'cat', '/opt/b02c/dns-hosting.json').stdout)
        hosts = [[hosting['ns1'], hosting['primary']], [hosting['ns2'], hosting['secondary']]]
        stage = 'wait for nameserver initialization'
        marker = '/run/registry-hosts-' + hosting['domain']
        for attempt in range(60):
            if docker(args.registry_container, 'test', '-f', marker + '.failed', check=False).returncode == 0:
                raise RuntimeError('Registry nameserver initialization failed; inspect /var/log/registry-hosts-' + hosting['domain'] + '.log')
            if docker(args.registry_container, 'test', '-f', marker + '.ready', check=False).returncode == 0:
                break
            if attempt == 59:
                raise RuntimeError('Registry nameserver initialization timed out')
            time.sleep(2)
        stage = 'verify nameserver hosts'
        # 环境变量仅传递非敏感拓扑信息。 / Environment variables carry only non-secret topology metadata.
        result = subprocess.run([
            'docker', 'exec', '-i', '-e', 'B02C_HOSTS=' + json.dumps(hosts),
            '-e', 'B02C_REGISTRAR=' + hosting['registrar'], '-e', 'B02C_PARENT=' + hosting['domain'],
            '-e', 'B02C_CHECK_ONLY=1', args.registry_container, 'php8.5'],
            input=DnsFileTemplates['setup-hosts-registry.php'], text=True, capture_output=True, timeout=60)
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or 'Registry host initialization failed')
        sys.stdout.write(result.stdout)
        credentials = {'product_id': args.product_id}
        stage = 'verify BIND APIs'
        for role, container in [('primary', args.primary_container), ('secondary', args.secondary_container)]:
            credentials[role] = read_credentials(container, role)
            wait_for_api(args.container, hosting[role])
        stage = 'configure DNS Hosting product'
        result = docker(args.container, 'php8.5', '-r', DnsFileTemplates['setup-product-fossbilling.php'],
                        input_text=json.dumps(credentials), check=False)
        if result.stdout:
            sys.stdout.write(result.stdout)
        if result.returncode:
            # 产品模板只输出不含认证信息的错误。 / The product template emits credential-free errors only.
            raise RuntimeError(result.stderr.strip() or 'DNS Hosting product initialization failed')
        return 0
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as error:
        detail = str(error) if isinstance(error, RuntimeError) else type(error).__name__
        print(f'FAIL DNS Hosting ({stage}): {detail}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
