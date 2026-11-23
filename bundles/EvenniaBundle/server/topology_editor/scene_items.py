"""Add missing fixture items while respecting later edits, moves and deletions."""
from collections import defaultdict

from django.db import transaction
from evennia.server.models import ServerConfig
from evennia.utils import logger

from .views import CATEGORY, is_area, parent_id, room_objects, save_item

ITEM_HISTORY = 'emuvista_scene_item_ids'


def place_item(key, spec, room, existing=None):
    obj = save_item(existing, room, spec['name'], spec['description'],
                    spec['portable'], spec['actions'])
    obj.attributes.add('map_item_key', key, category=CATEGORY)
    return obj


def existing_locations(document, needed):
    """Older imported worlds have no portable map keys. Match their full paths."""
    children = defaultdict(list)
    for obj in room_objects().values():
        kind = 'area' if is_area(obj) else 'room'
        children[parent_id(obj), obj.key, kind].append(obj)
    specs = {node['key']: node for node in document['nodes']}
    found = {}
    for key in needed:
        path = []
        node = specs[key]
        while node:
            path.append(node)
            node = specs.get(node['parent'])
        parent = None
        for part in reversed(path):
            matches = children[parent, part['name'], part['kind']]
            if len(matches) != 1:
                break
            parent = matches[0].id
        else:
            found[key] = matches[0]
    return found


def seed_items(document, items, locations=None):
    with transaction.atomic():
        applied = set(ServerConfig.objects.conf(ITEM_HISTORY, default=[]))
        pending = items.keys() - applied
        if not pending:
            return
        if locations is None:
            locations = existing_locations(document, {items[key]['room'] for key in pending})
        for key, item in items.items():
            if key not in pending:
                continue
            room = locations.get(item['room'])
            if room is None:
                logger.log_warn(f"Skipping scene item {key}: cannot uniquely locate {item['room']}.")
                continue
            place_item(key, item, room)
            applied.add(key)
        ServerConfig.objects.conf(ITEM_HISTORY, value=sorted(applied))
