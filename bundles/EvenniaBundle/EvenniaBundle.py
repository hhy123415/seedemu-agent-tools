"""One persistent Evennia world, standalone or attached to SEED networks."""
from pathlib import Path
import re
import json
import shutil

from seedemu.containerBundle import ContainerBundle
from seedemu.containerBundle.ContainerBundle import PreparedContainer
from seedemu.core.Volume import BaseVolume

from .server.topology_editor.schema import validate_map

SERVER_SOURCE = Path(__file__).parent / 'server'


def stage_server(destination, map_import=None):
    shutil.copytree(SERVER_SOURCE, destination, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns('__pycache__'))
    (Path(destination) / 'map-import.json').write_text(
        json.dumps(map_import, ensure_ascii=False), encoding='utf-8')


class _EvenniaContainer(PreparedContainer):
    map_import = None

    def _generateDockerfile(self):
        stage_server(Path.cwd(), self.map_import)
        dockerfile = (SERVER_SOURCE / 'Dockerfile').read_text()
        for filename, content in self._files.items():
            dockerfile += self._addFile(filename, content) + '\n'
        return dockerfile


class EvenniaBundle(ContainerBundle):
    """Manage Portal, Server and SQLite together in a single container."""

    def __init__(self, emulator=None, name='evennia'):
        if not re.fullmatch(r'[a-z][a-z0-9-]{0,31}', name):
            raise ValueError('name must contain 1 to 32 lowercase letters, digits or hyphens')
        super().__init__(emulator=emulator)
        self._name = name
        self._volume = name + '-data'
        self._save_path = None
        self._host_ports = None
        self._environment = {}
        self._required_internal_address_count = 1
        self._containers = {'server': _EvenniaContainer(name=name, emulator=emulator)}

    def setSuperuser(self, username, password, email=''):
        """Credentials used only when initializing a new world."""
        if not username or not password:
            raise ValueError('superuser username and password must not be empty')
        self._environment.update(EVENNIA_SUPERUSER_USERNAME=str(username),
                                 EVENNIA_SUPERUSER_PASSWORD=str(password),
                                 EVENNIA_SUPERUSER_EMAIL=str(email))
        return self

    def importMap(self, path, mode='append', spawn=None):
        """Import this map once per world/configuration when the server starts.

        append keeps existing rooms; replace reuses the default room for spawn
        (a physical room key in the JSON) and relocates existing occupants there.
        Changing the map or mode creates a new import on the next deployment.
        """
        path = Path(path)
        if path.stat().st_size > 1024 * 1024:
            raise ValueError('map file must not exceed 1 MiB')
        document = validate_map(json.loads(path.read_text(encoding='utf-8-sig')))
        if mode not in ('append', 'replace'):
            raise ValueError('map mode must be append or replace')
        if mode == 'replace' and spawn not in {
                n['key'] for n in document['nodes'] if n['kind'] == 'room'}:
            raise ValueError('replace requires spawn to name a physical room key in the map')
        if mode == 'append' and spawn is not None:
            raise ValueError('spawn is only supported in replace mode')
        self.getContainer('server').map_import = {
            'document': document, 'mode': mode, 'spawn': spawn}
        return self

    def enableHostAccess(self, web_port=4001, websocket_port=4002, telnet_port=4000):
        ports = tuple(int(port) for port in (web_port, websocket_port, telnet_port))
        if any(not 1 <= port <= 65535 for port in ports) or len(set(ports)) != 3:
            raise ValueError('host ports must be distinct and between 1 and 65535')
        self._host_ports = ports
        self._environment['WEBSOCKET_CLIENT_PROXY_PORT'] = str(ports[1])
        return self

    def setDataVolume(self, name):
        if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.-]*', name):
            raise ValueError('invalid Docker volume name')
        self._volume, self._save_path = name, None
        return self

    def setSavePath(self, path):
        self._save_path = Path(path).resolve()
        return self

    def getVolumes(self):
        return {} if self._save_path else {self._volume: {'name': self._volume}}

    def registerVolumes(self, compiler):
        if not self._save_path:
            compiler._addVolume(BaseVolume(type='volume', source=self._volume,
                                           name=self._volume, target='/data'))

    def _service(self):
        if 'EVENNIA_SUPERUSER_PASSWORD' not in self._environment:
            raise ValueError('call setSuperuser() before generating the bundle')
        if self._save_path:
            self._save_path.mkdir(parents=True, exist_ok=True)
        config = {
            'init': True,
            'environment': {key: value.replace('$', '$$')
                            for key, value in self._environment.items()},
            'volumes': [f'{self._save_path or self._volume}:/data'],
            'stop_grace_period': '60s',
        }
        if self._host_ports:
            config['ports'] = [f'127.0.0.1:{host}:{internal}' for host, internal in
                               zip(self._host_ports, (4001, 4002, 4000))]
        return config

    def prepare(self, output, context_name='evennia'):
        """Stage standalone build context; caller declares getVolumes() in Compose."""
        if not re.fullmatch(r'[a-zA-Z0-9_-]+', context_name):
            raise ValueError('context_name must be a simple directory name')
        config = self._service()
        stage_server(Path(output) / context_name, self.getContainer('server').map_import)
        return {'build': './' + context_name, **config}

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
        container.setEntrypointWrapper('/opt/evennia/start.sh', [])
        config = self._service()
        if container._default_route:
            config['cap_add'] = ['NET_ADMIN']
        container.updateServiceConfig(config)
        return super().install()
