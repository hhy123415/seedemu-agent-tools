#!/usr/bin/env python3
"""Verify checkout connectivity and the automatically enabled gateway."""
import argparse
import json
import subprocess
import sys
import time
from urllib.parse import urlsplit


def execute(container, command, payload=None):
    """Execute a container command without exposing input or sensitive output in errors."""
    result = subprocess.run(['docker', 'exec', '-i', container, *command], input=payload,
                            capture_output=True, text=True, timeout=30)
    if result.returncode:
        operation = {'cat': 'configuration read', 'curl': 'checkout health request',
                     'php8.5': 'FOSSBilling gateway verification'}.get(command[0], 'container command')
        raise RuntimeError(f'{operation} failed (exit {result.returncode}); inspect container startup logs')
    return result.stdout


def setup(billing, payment, timeout):
    """Validate configuration, health, and the enabled gateway; do not create or pay invoices."""
    secret = execute(billing, ['cat', '/opt/fake-payment/payment-secret']).strip()
    if not secret or secret != execute(payment, ['cat', '/opt/fake-payment/secret']).strip():
        raise RuntimeError('Checkout and registrar signing secrets do not match')
    config = json.loads(execute(billing, ['cat', '/opt/fake-payment/payment-config.json']))
    if config != json.loads(execute(payment, ['cat', '/opt/fake-payment/payment-config.json'])):
        raise RuntimeError('Checkout and registrar payment configurations do not match')
    url = urlsplit(config['payment_url'])
    health = f'{url.scheme}://{url.netloc}/health'
    deadline = time.monotonic() + timeout
    while True:
        try:
            if execute(billing, ['curl', '-fsS', '--max-time', '3', health]).strip() == 'ok':
                break
        except (RuntimeError, subprocess.TimeoutExpired):
            pass
        if time.monotonic() >= deadline:
            raise RuntimeError('Checkout health check timed out from registrar')
        time.sleep(min(2, max(0, deadline - time.monotonic())))
    # Startup enables the gateway; only verify its state here.
    deadline = time.monotonic() + timeout
    while True:
        status = execute(billing, ['sh', '-c', 'if [ -f /run/fake-payment-initialization.failed ]; then echo failed; elif [ -f /run/fake-payment-initialized ]; then echo ready; fi']).strip()
        if status == 'ready':
            break
        if status == 'failed' or time.monotonic() >= deadline:
            raise RuntimeError('Gateway initialization failed or timed out; inspect /var/log/fake-payment-initialize.log')
        time.sleep(min(2, max(0, deadline - time.monotonic())))
    output = execute(billing, ['env', 'FAKE_PAYMENT_CHECK_ONLY=1', 'php8.5', '/opt/fake-payment/setup-gateway.php'])
    if 'PASS' not in output:
        raise RuntimeError('Gateway verification did not confirm success')
    sys.stdout.write(output)


def main(argv=None):
    """Parse container arguments and report initialization results."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--container', required=True)
    parser.add_argument('--payment-container', required=True)
    parser.add_argument('--timeout', type=int, default=120)
    args = parser.parse_args(argv)
    if args.timeout <= 0:
        parser.error('--timeout must be positive')
    try:
        setup(args.container, args.payment_container, args.timeout)
        return 0
    except (OSError, RuntimeError, ValueError, KeyError, subprocess.TimeoutExpired) as error:
        print(f'模拟支付初始化失败 / FakePayment setup failed: {type(error).__name__}: '
              + (str(error) if isinstance(error, RuntimeError) else 'Check container configuration and availability'), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
