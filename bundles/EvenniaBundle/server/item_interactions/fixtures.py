"""Validate scene items during bundle compilation, before starting Evennia."""
from .actions import validate_actions


def validate_items(items, document):
    rooms = {node['key'] for node in document['nodes'] if node['kind'] == 'room'}
    if not isinstance(items, dict):
        raise ValueError('场景物品必须是以稳定标识为键的对象。')
    for key, item in items.items():
        if not isinstance(key, str) or not key.strip() or not isinstance(item, dict):
            raise ValueError('场景物品标识或配置无效。')
        if not isinstance(item.get('room'), str) or item['room'] not in rooms:
            raise ValueError(f'{key} 的 room 必须引用地图中的可站立地点。')
        for field, limit in [('name', 255), ('description', 20000)]:
            value = item.get(field)
            if not isinstance(value, str) or len(value) > limit or (field == 'name' and not value.strip()):
                raise ValueError(f'{key} 的 {field} 无效。')
        if type(item.get('portable')) is not bool:
            raise ValueError(f'{key} 的 portable 必须为布尔值。')
        validate_actions(item.get('actions'))
    return items
