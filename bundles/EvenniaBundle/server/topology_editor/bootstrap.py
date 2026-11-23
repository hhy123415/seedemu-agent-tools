"""Apply a bundled map once, after Evennia has initialized the world."""
import hashlib
import json
from pathlib import Path

from django.conf import settings
from django.db import transaction
from evennia.server.models import ServerConfig
from evennia.utils import logger

from .transfer import import_map

IMPORT_HISTORY = 'emuvista_map_imports'


def at_server_start():
    path = Path(getattr(settings, 'EMUVISTA_MAP_IMPORT_FILE', '/opt/evennia/map-import.json'))
    if not path.exists():
        return
    config = json.loads(path.read_text(encoding='utf-8'))
    if config is None:
        return
    fingerprint = hashlib.sha256(json.dumps(
        config, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()
    applied = list(ServerConfig.objects.conf(IMPORT_HISTORY, default=[]))
    if fingerprint in applied:
        return
    with transaction.atomic():
        result = import_map(config['document'], config['mode'], config.get('spawn'))
        ServerConfig.objects.conf(IMPORT_HISTORY, value=[*applied, fingerprint])
    logger.log_info(f"EmuVista bundled map imported ({config['mode']}): {result}")
