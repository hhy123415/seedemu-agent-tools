#!/usr/bin/env python3
"""等待 FOSSBilling 自动初始化，再验证 EPP 与客户登录。
Wait for automatic FOSSBilling initialization, then verify EPP and client logins.
"""
from __future__ import annotations
import argparse
import base64
import json
import subprocess
import sys
import time

if __package__:
    from .template import FossBillingFileTemplates
else:
    from template import FossBillingFileTemplates

LOCAL_URL = 'http://127.0.0.1:8080'


def php_json(value):
    """安全嵌入 JSON，避免 PHP 字符串变量展开。 / Embed JSON safely without PHP string interpolation."""
    encoded = base64.b64encode(json.dumps(value).encode()).decode('ascii')
    return "json_decode(base64_decode('" + encoded + "'), true, 512, JSON_THROW_ON_ERROR)"


def docker(container: str, *command: str, input_text: str | None = None,
           check: bool = True) -> subprocess.CompletedProcess[str]:
    """在指定容器内执行命令，并捕获输出以检查执行结果。 / Run a command in the selected container and capture its output."""
    return subprocess.run(
        ["docker", "exec", *(["-i"] if input_text is not None else []), container, *command],
        input=input_text, text=True, capture_output=True, check=check, timeout=200,
    )


def verify_epp(container: str) -> None:
    """通过 Namingo 适配器登录专用 EPP，确认端口和凭据可用。 / Log in through the Namingo adapter to verify EPP connectivity and credentials."""
    connection = json.loads(docker(
        container, "cat", "/opt/b02b-fossbilling/epp-connection.json"
    ).stdout)
    php = FossBillingFileTemplates['verify-epp.php']
    php = php.replace("CONNECTION_PLACEHOLDER", php_json(connection))
    last_error = ""
    for attempt in range(120):
        result = docker(container, "php8.5", input_text=php, check=False)
        if result.returncode == 0:
            sys.stdout.write(result.stdout)
            return
        last_error = result.stderr.strip() or result.stdout.strip()
        if attempt < 119:
            time.sleep(2)
    raise RuntimeError("Dedicated EPP login failed: " + last_error)


def verify_login(container: str, email: str, password: str) -> None:
    """调用客户登录 API，确认账号可以实际登录。 / Call the client login API to verify the account."""
    response = docker(
        container, "curl", "-sS", "--max-time", "30", "-X", "POST",
        f"{LOCAL_URL}/api/guest/client/login",
        "--data-urlencode", f"email={email}",
        "--data-urlencode", f"password={password}",
    )
    payload = json.loads(response.stdout)
    if payload.get("error") or not payload.get("result"):
        raise RuntimeError("Client login failed: " + response.stdout[:500])


def wait_for_initialization(container):
    """有界等待本地启动任务，失败时立即报告日志位置。 / Wait with a bound and report local initialization failures immediately."""
    for attempt in range(120):
        if docker(container, 'test', '-f', '/run/fossbilling-initialization.failed', check=False).returncode == 0:
            raise RuntimeError('FOSSBilling initialization failed; inspect /var/log/fossbilling-initialize.log')
        if docker(container, 'test', '-f', '/run/fossbilling-initialized', check=False).returncode == 0:
            return
        if attempt < 119:
            time.sleep(2)
    raise RuntimeError('FOSSBilling initialization timed out; inspect /var/log/fossbilling-initialize.log')


def main():
    """只验证服务运行结果，不修改本地账号或配置。 / Verify running services without changing local accounts or configuration."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--container', required=True)
    args = parser.parse_args()
    try:
        wait_for_initialization(args.container)
        settings = json.loads(docker(args.container, 'cat', '/opt/b02b-fossbilling/setup-config.json').stdout)
        verify_epp(args.container)
        verify_login(args.container, settings['client_email'], settings['client_password'])
    except (OSError, subprocess.SubprocessError, RuntimeError, ValueError, KeyError) as error:
        print(str(error) if isinstance(error, RuntimeError) else 'FOSSBilling verification failed; inspect container logs.', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
