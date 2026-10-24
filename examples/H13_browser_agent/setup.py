#!/usr/bin/env python3
"""Initialize domain services and verify the colocated browser and agent."""
import argparse
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent


# Connect to Playwright to verify the browser without performing purchases.
CHECK = """
import asyncio
from urllib.request import urlopen
from playwright.async_api import async_playwright
from browser_runtime.control import connection_config

async def check():
    for attempt in range(30):
        try:
            assert urlopen('http://127.0.0.1:8089/', timeout=2).status == 200
            async with async_playwright() as p:
                browser = await p.chromium.connect(connection_config()['ws_endpoint'], timeout=2000)
                await browser.close()
            return
        except Exception:
            if attempt == 29:
                raise
            await asyncio.sleep(2)

asyncio.run(check())
"""


def main(argv=None):
    """Reuse H12 setup and then verify browser connectivity."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=HERE / 'output')
    parser.add_argument('--dns-product-id', type=int)
    parser.add_argument('--timeout', type=int, default=240)
    args = parser.parse_args(argv)
    output = args.output.resolve()
    command = [sys.executable, str(HERE.parent / 'H12_domain_name_purchase/setup.py'),
               '--output', str(output), '--timeout', str(args.timeout)]
    if args.dns_product_id is not None:
        command += ['--dns-product-id', str(args.dns_product_id)]
    try:
        subprocess.run(command, check=True)
        subprocess.run(['docker', 'compose', 'exec', '-T', 'browser-agent',
                        '/opt/venv/bin/python', '-c', CHECK], cwd=output, check=True)
        return 0
    except subprocess.CalledProcessError as error:
        return error.returncode if error.returncode > 0 else 1
    except OSError as error:
        print(error, file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
