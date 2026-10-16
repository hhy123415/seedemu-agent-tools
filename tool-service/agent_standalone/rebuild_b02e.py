#!/usr/bin/env python3
"""清除本地 B00/B02 场景容器和卷，重新生成、构建并初始化 B02e。

运行：python3 agent_standalone/rebuild_b02e.py
仅预览：python3 agent_standalone/rebuild_b02e.py --dry-run
继续初始化现有容器：python3 agent_standalone/rebuild_b02e.py --setup-only
保留镜像构建缓存；场景数据库随容器/卷删除。不会执行全局 Docker prune。
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
# 与在 B02e output 目录手动执行 docker compose up 的项目名保持一致。
PROJECT = 'output'


def run(command, *, capture=False, cwd=None):
    return subprocess.run([str(x) for x in command], check=True, text=True,
                          capture_output=capture, cwd=cwd)


def cleanup_projects(containers, internet):
    """执行项目级 down --remove-orphans 前，检查每个容器的归属。"""
    groups = {}
    for container in containers:
        labels = container.get('Config', {}).get('Labels') or {}
        project = labels.get('com.docker.compose.project')
        if project:
            groups.setdefault(project, []).append(labels)

    def recognized(label):
        paths = label.get('com.docker.compose.project.config_files', '').split(',')
        for value in paths:
            path = Path(value).resolve()
            try:
                relative = path.relative_to(internet)
            except ValueError:
                return False
            if (len(relative.parts) != 3 or relative.parts[1:] != ('output', 'docker-compose.yml')
                    or not relative.parts[0].startswith(('B00_', 'B02'))):
                return False
        return True

    result = []
    for project, members in groups.items():
        if not any(recognized(label) for label in members) and project != PROJECT:
            continue
        if not all(recognized(label) for label in members):
            raise RuntimeError(f'Compose 项目 {project} 混入其他目录的容器，拒绝清除')
        paths = [Path(label['com.docker.compose.project.config_files'].split(',')[0])
                 for label in members]
        existing = next((path for path in paths if path.is_file()), None)
        # 场景改名或删除后，Compose 标签可能仍指向已不存在的路径。
        # 上方已验证所有容器的归属，因此可使用当前配置清理同一项目及其孤立服务。
        if existing is None:
            current = internet / 'B02e_with_browser/output/docker-compose.yml'
            if current.is_file():
                existing = current
        if existing is None:
            raise RuntimeError(f'项目 {project} 的 Compose 文件已丢失，无法安全清除')
        result.append((project, existing))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    default_repo = next((parent / 'seed-emulator' for parent in ROOT.parents
                         if (parent / 'seed-emulator').is_dir()), None)
    parser.add_argument('--seed-emulator', type=Path, default=default_repo)
    parser.add_argument('--python', type=Path, help='SeedEmu Python，默认使用仓库 .venv/bin/python')
    parser.add_argument('--setup-only', action='store_true', help='只执行 setup 脚本，保留现有容器及数据')
    parser.add_argument('--dry-run', action='store_true', help='仅打印执行计划及清理范围')
    args = parser.parse_args()
    if args.seed_emulator is None:
        parser.error('请指定 --seed-emulator 路径')
    repo = args.seed_emulator.resolve()
    python = (args.python or repo / '.venv/bin/python').absolute()
    internet = repo / 'examples/internet'
    scenario = internet / 'B02e_with_browser'
    output = scenario / 'output'
    setups = [internet / 'B02b_with_fossbilling/setup_registry.py',
              internet / 'B02b_with_fossbilling/setup_fossbilling.py',
              internet / 'B02c_with_dns_publication/setup_hosts_registry.py',
              internet / 'B02c_with_dns_publication/setup_dns_hosting_fossbilling.py',
              internet / 'B02d_with_fake_payment/setup_fake_payment_fossbilling.py']
    for path in [python, scenario / 'with_browser.py', *setups]:
        if not path.is_file():
            raise RuntimeError(f'缺少文件：{path}')
    if args.setup_only:
        print('继续初始化现有 B02e 容器；保留容器和数据库', flush=True)
    else:
        ids = run(['docker', 'ps', '-aq'], capture=True).stdout.split()
        containers = json.loads(run(['docker', 'inspect', *ids], capture=True).stdout) if ids else []
        cleanup = cleanup_projects(containers, internet)
        print('将删除以下场景项目的容器、网络和卷（包括数据库）：', flush=True)
        for project, path in cleanup:
            print(f'  {project}: {path}', flush=True)
        print(f'重新生成并启动 {scenario}；Compose 项目：{PROJECT}', flush=True)
    if not args.setup_only:
        print('启动命令：docker compose up -d --build（在 B02e/output 目录）', flush=True)
    print('setup 顺序：Registry → FOSSBilling → DNS hosts → DNS Hosting → FakePayment', flush=True)
    if args.dry_run:
        return 0

    if not args.setup_only:
        # 先渲染，避免 Python 或导入错误导致已有部署被提前删除。
        run([python, 'with_browser.py'], cwd=scenario)
        for project, path in cleanup:
            run(['docker', 'compose', '-p', project, '-f', path, 'down', '--volumes', '--remove-orphans'])
        run(['docker', 'compose', 'up', '-d', '--build'], cwd=output)

    for setup in setups:
        run([python, setup.name], cwd=setup.parent)
    print('完成：全部 setup 脚本执行成功')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(f'FAIL: {error}', file=sys.stderr)
        raise SystemExit(1)
