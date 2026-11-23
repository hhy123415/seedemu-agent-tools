"""Standalone Mindcraft execution with reusable service-owned tool packages."""
from __future__ import annotations

from pathlib import Path
import json
import re
import shutil

from services.AgentService.ToolPackage import ToolPackage

RUNTIME = Path(__file__).parent / 'runtime'


class MinecraftAgentService:
    """Prepare Mindcraft containers and isolated per-player persistence for Compose.

    This replaces the old SEED AgentService subclass. The native Mindcraft loop
    owns agent execution; experiments own goals, map data and deployment topology.
    """

    def __init__(self, environment_file, *, minecraft_host='minecraft',
                 minecraft_port=25565, minecraft_version='1.21.6'):
        self._environment_file = Path(environment_file).resolve()
        if not self._environment_file.is_file():
            raise ValueError(f'environment file not found: {self._environment_file}')
        if not 1 <= int(minecraft_port) <= 65535:
            raise ValueError('Minecraft port must be between 1 and 65535')
        self._host = str(minecraft_host)
        self._port = int(minecraft_port)
        self._version = str(minecraft_version)
        self._agents = {}
        self._regions = None
        self._tool_packages = {}

    def registerTools(self, package):
        """Register a ToolPackage or a bundle's getAgentTools() export.

        addAgent(accounts=..., tools=[...]) supplies private identities and grants.
        Handlers receive accounts, tool_config and the authorized tools registry;
        packages needing additional Python/system dependencies require image support.
        """
        package = ToolPackage(**package) if isinstance(package, dict) else package
        if not isinstance(package, ToolPackage):
            raise TypeError('expected ToolPackage or getAgentTools() export')
        if package.name in self._tool_packages:
            raise ValueError('duplicate tool package: ' + package.name)
        self._tool_packages[package.name] = package
        return self

    def setRegionPath(self, path):
        self._regions = Path(path).resolve()
        if not self._regions.is_dir():
            raise ValueError(f'region directory not found: {self._regions}')
        return self

    def addAgent(self, name, *, persona_file, ui_port=None, service_name=None,
                 container_name=None, volume=None, accounts=None, tools=()):
        if not re.fullmatch(r'[A-Za-z0-9_]{1,16}', name):
            raise ValueError('Minecraft name must contain 1 to 16 letters, digits or underscores')
        service_name = service_name or name.lower()
        container_name = container_name or 'mindcraft-' + service_name
        volume = volume or 'mindcraft-' + service_name
        for identifier in (service_name, container_name, volume):
            if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.-]*', identifier):
                raise ValueError(f'invalid Compose identifier: {identifier}')
        if ui_port is not None and not 1 <= int(ui_port) <= 65535:
            raise ValueError('UI port must be between 1 and 65535')
        ui_port = int(ui_port) if ui_port is not None else None
        for other in self._agents.values():
            if (other['name'].lower() == name.lower() or other['service'] == service_name
                    or other['container'] == container_name or other['volume'] == volume
                    or (ui_port is not None and other['ui_port'] == ui_port)):
                raise ValueError('agents require unique names, services, containers, memory volumes and UI ports')
        task = Path(persona_file).resolve()
        if not task.is_file():
            raise ValueError(f'persona configuration not found: {task}')
        self._agents[service_name] = dict(name=name, task=task, service=service_name,
                                        container=container_name, volume=volume, ui_port=ui_port,
                                        accounts=json.loads(json.dumps(accounts or {})), tools=list(tools))
        return self

    def getVolumes(self):
        return {agent['volume']: {'name': agent['volume']} for agent in self._agents.values()}

    def prepare(self, output, *, context_name='mindcraft', minecraft_service=None):
        """Return a Compose fragment with services and volumes, staging only code.

        Credentials and task configurations are referenced at runtime, never
        copied into the image. minecraft_service optionally adds a health dependency.
        """
        if not self._agents:
            raise ValueError('add at least one agent before preparing services')
        if not re.fullmatch(r'[a-zA-Z0-9_-]+', context_name):
            raise ValueError('context_name must be a simple directory name')
        if minecraft_service in self._agents:
            raise ValueError('Minecraft server and agent service names must differ')
        output = Path(output).resolve()
        if output == self._environment_file or output in self._environment_file.parents:
            raise ValueError('environment file must be outside generated output')
        context = output / context_name
        shutil.copytree(RUNTIME, context, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        # Reuse the framework-neutral registry and HTTP helpers, not the agent loop.
        shared = Path(__file__).parents[1] / 'AgentService' / 'runtime' / 'emuvista_agent'
        shutil.copytree(shared, context / 'emuvista_agent', dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        packages = context / 'packages'
        if packages.exists():
            shutil.rmtree(packages)
        packages.mkdir()
        definitions = set()
        for package in self._tool_packages.values():
            if package.requirements or package.software:
                raise ValueError('tool dependencies must be supplied by the Mindcraft image')
            for source, relative in package.files():
                target = packages / package.name / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
            definitions.update(item['name'] for item in package.manifest)
        configuration_dir = output / 'tool-config'
        configuration_dir.mkdir(exist_ok=True, mode=0o700)
        services = {}
        for key, agent in self._agents.items():
            if set(agent['tools']) - definitions:
                raise ValueError('agent grants tools that are not registered')
            tool_configuration = configuration_dir / (key + '.json')
            tool_configuration.write_text(json.dumps({
                'root': '/mindcraft', 'packages': list(self._tool_packages),
                'allowed_tools': agent['tools'], 'accounts': agent['accounts'],
                'tool_config': {name: package.configuration for name, package in self._tool_packages.items()},
            }) + '\n')
            tool_configuration.chmod(0o600)
            environment = {
                'AGENT_NAME': agent['name'], 'MC_HOST': self._host, 'MC_PORT': str(self._port),
                'MC_VERSION': self._version, 'NODE_OPTIONS': '--dns-result-order=ipv4first',
                # 独立容器忽略同组其他 agent 的公开聊天，保留 E17 的防循环行为。
                'MINDCRAFT_IGNORED_PLAYERS': ','.join(
                    other['name'] for other in self._agents.values() if other is not agent),
            }
            service = {
                'build': './' + context_name, 'container_name': agent['container'],
                'env_file': [str(self._environment_file)], 'environment': environment,
                'volumes': [f'{agent["volume"]}:/app/bots/{agent["name"]}',
                            f'{agent["task"]}:/mindcraft/persona.json:ro',
                            f'{tool_configuration}:/mindcraft/tools.json:ro'],
                'init': True, 'stop_grace_period': '30s',
            }
            if self._regions is not None:
                environment['SEMANTIC_REGIONS_DIR'] = '/map/regions'
                service['volumes'].append(f'{self._regions}:/map/regions:ro')
            if agent['ui_port'] is not None:
                service['ports'] = [f'127.0.0.1:{agent["ui_port"]}:8081']
            if minecraft_service is not None:
                service['depends_on'] = {minecraft_service: {'condition': 'service_healthy'}}
            services[key] = service
        return {'services': services, 'volumes': self.getVolumes()}
