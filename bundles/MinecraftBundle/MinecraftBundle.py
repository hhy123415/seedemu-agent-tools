"""Paper server with WorldEdit, WorldGuard and semantic map synchronization."""
from __future__ import annotations

import hashlib
from pathlib import Path
import re
import shutil
import uuid

from seedemu.containerBundle import ContainerBundle
from seedemu.containerBundle.ContainerBundle import PreparedContainer
from seedemu.core.Volume import BaseVolume

MINECRAFT_VERSION = '1.21.6'
SERVER_SOURCE = Path(__file__).parent / 'server'


def find_world(directory):
    directory = Path(directory).resolve()
    if (directory / 'level.dat').is_file():
        return directory
    candidates = sorted(p.parent for p in directory.glob('*/level.dat') if p.is_file())
    if len(candidates) != 1:
        raise ValueError(f'{directory} must contain level.dat or exactly one save folder; '
                         f'found {len(candidates)} saves')
    return candidates[0]


def stage_server(destination):
    shutil.copytree(SERVER_SOURCE, destination, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns('target', '.runtime', '__pycache__'))


class _ServerContainer(PreparedContainer):
    def _generateDockerfile(self):
        stage_server(Path.cwd())
        dockerfile = (SERVER_SOURCE / 'Dockerfile').read_text()
        if self._default_route:
            dockerfile += ('\nRUN apt-get update && apt-get install -y --no-install-recommends '
                           'iproute2 && rm -rf /var/lib/apt/lists/*\n')
        for filename, content in self._files.items():
            dockerfile += self._addFile(filename, content) + '\n'
        return dockerfile


class MinecraftBundle(ContainerBundle):
    """One reusable server, usable through SEED or standalone Compose."""

    def __init__(self, emulator=None, name='minecraft', resolver=None):
        if not re.fullmatch(r'[a-z][a-z0-9-]{0,31}', name):
            raise ValueError('bundle name requires 1 to 32 lowercase letters, digits or hyphens')
        super().__init__(emulator=emulator)
        self._name = name
        self._resolver = resolver
        self._host_port = None
        self._volume = name + '-data'
        self._save_path = None
        self._world = None
        self._regions = None
        self._environment = {
            'EULA': 'TRUE', 'TYPE': 'PAPER', 'VERSION': MINECRAFT_VERSION,
            'PAPER_BUILD': '48', 'MEMORY': '2G', 'ONLINE_MODE': 'FALSE',
            'SERVER_PORT': '25565', 'MODE': 'survival', 'DIFFICULTY': 'easy',
            'SPAWN_PROTECTION': '0', 'ENABLE_RCON': 'true', 'MOTD': 'EmuVista Minecraft',
        }
        self._required_internal_address_count = 1
        self._containers = {'server': _ServerContainer(name=name, emulator=emulator)}

    def enableHostAccess(self, port=25565):
        if not 1 <= int(port) <= 65535:
            raise ValueError('host port must be between 1 and 65535')
        self._host_port = int(port)
        return self

    def setDataVolume(self, name):
        if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.-]*', name):
            raise ValueError('invalid Docker volume name')
        self._volume, self._save_path = name, None
        return self

    def setSavePath(self, path):
        self._save_path = Path(path).resolve()
        return self

    def setWorld(self, path):
        self._world = find_world(path)
        return self

    def setRegionPath(self, path):
        self._regions = Path(path).resolve()
        return self

    def setOperators(self, names):
        # 离线用户名大小写敏感；避免服务端按正版账号查询 UUID。
        identifiers = [str(uuid.UUID(bytes=hashlib.md5(
            ('OfflinePlayer:' + name).encode('utf-8')).digest(), version=3)) for name in names]
        self._environment.update(OPS=','.join(identifiers), OP_PERMISSION_LEVEL='4',
                                 EXISTING_OPS_FILE='MERGE')
        return self

    def configureApplication(self, environment):
        reserved = {'TYPE', 'VERSION', 'PAPER_BUILD', 'SERVER_PORT', 'WORLD', 'LEVEL',
                    'FORCE_WORLD_COPY', 'ONLINE_MODE'}
        if reserved.intersection(environment):
            raise ValueError('server version, offline mode and world import are managed by the bundle')
        self._environment.update({key: str(value) for key, value in environment.items()})
        return self

    def _service(self):
        environment = dict(self._environment)
        if self._save_path:
            self._save_path.mkdir(parents=True, exist_ok=True)
        volumes = [f'{self._save_path or self._volume}:/data']
        if self._world:
            environment.update(WORLD='/world-source', LEVEL='imported_world', FORCE_WORLD_COPY='FALSE')
            volumes.append(f'{self._world}:/world-source:ro')
        if self._regions:
            self._regions.mkdir(parents=True, exist_ok=True)
            volumes.append(f'{self._regions}:/data/plugins/SemanticRegions/regions')
        service = {
            'environment': {key: value.replace('$', '$$') for key, value in environment.items()},
            'volumes': volumes, 'stop_grace_period': '2m',
            'healthcheck': {'test': ['CMD', 'mc-health'], 'interval': '10s',
                            'timeout': '5s', 'retries': 12, 'start_period': '5m'},
        }
        if self._host_port is not None:
            service['ports'] = [f'{self._host_port}:25565']
        if self._resolver:
            service['dns'] = [self._resolver]
        return service

    def prepare(self, output, context_name='server', container_name=None):
        """Stage a standalone Compose build context and return its service mapping.

        Callers using named persistence must also declare getVolumes() at Compose root.
        """
        if not re.fullmatch(r'[a-zA-Z0-9_-]+', context_name):
            raise ValueError('context_name must be a simple directory name')
        stage_server(Path(output) / context_name)
        return {'build': './' + context_name, 'container_name': container_name or self._name,
                **self._service()}

    def getVolumes(self):
        return {} if self._save_path else {self._volume: {'name': self._volume}}

    def registerVolumes(self, compiler):
        """Register named persistence with the SEED Docker compiler."""
        if not self._save_path:
            compiler._addVolume(BaseVolume(type='volume', source=self._volume,
                                           name=self._volume, target='/data'))

    def configure(self):
        if self._is_configured:
            return
        container = self.getContainer('server')
        for network in self.getInternalNetworks():
            container.joinInternalNetwork(network['asn'], network['network_name'],
                                          network['ip_addresses'][0], self._name,
                                          network['default_route'])
        super().configure()

    def install(self):
        self.configure()
        container = self.getContainer('server')
        container.setEntrypointWrapper('/semantic-start.sh', [])
        config = self._service()
        if container._default_route:
            config['cap_add'] = ['NET_ADMIN']
        container.updateServiceConfig(config)
        return super().install()
