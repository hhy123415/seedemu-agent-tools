"""Portable map documents with append and explicit whole-map replacement."""

from django.conf import settings
from django.db import transaction
from evennia.objects.models import ObjectDB
from evennia.typeclasses.attributes import Attribute
from evennia.utils.create import create_object

from item_interactions.fixtures import validate_items

from .views import CATEGORY, InvalidEdit, keyed_floor_items, protected_ids, room_objects, snapshot

from .scene_items import place_item, seed_items
from .schema import FORMAT, validate_map, summary


def export_map():
    state = snapshot()
    key = lambda ident: f'room-{ident}' if ident is not None else None
    return {
        'format': FORMAT, 'version': 1,
        'nodes': [{'key': key(n['id']), 'name': n['name'], 'kind': n['kind'],
                   'description': n['description'], 'parent': key(n['parent']),
                   'entry': key(n['entry'])}
                  for n in state['nodes']],
        'connections': [{'source': key(e['source']),
                         'target': key(e['area_target'] or e['target']), 'name': e['name']}
                        for e in state['edges']],
        'items': {
            item['map_key']: {'room': key(item['parent']), 'name': item['name'],
                              'description': item['description'], 'portable': item['portable'],
                              'actions': item['actions']}
            for item in state['items']
        },
    }


def replacement_plan(document, spawn):
    rooms = room_objects()
    candidates = {n['key']: n for n in document['nodes'] if n['kind'] == 'room'}
    if not isinstance(spawn, str) or spawn not in candidates:
        raise InvalidEdit('替换模式必须选择一个导入的可站立地点作为安置地点。')
    anchors = [rooms[ident] for ident in protected_ids() if ident in rooms]
    if len(anchors) != 1 or anchors[0].is_typeclass('topology_editor.rooms.Area', exact=False):
        raise InvalidEdit('替换要求默认出生点与回家地点指向同一个有效的普通房间。')
    if protected_ids() != {anchors[0].id}:
        raise InvalidEdit('默认出生点或回家地点引用失效，无法替换。')
    all_objects = list(ObjectDB.objects.all())
    exits = [obj for obj in all_objects
             if obj.is_typeclass('evennia.objects.objects.DefaultExit', exact=False)
             and (obj.db_location_id in rooms or obj.db_destination_id in rooms)]
    excluded = set(rooms) | {obj.id for obj in exits}
    occupants = [obj for obj in all_objects if obj.id not in excluded and obj.db_location_id in rooms]
    homes = [obj for obj in all_objects if obj.id not in excluded and obj.db_home_id in rooms]
    destinations = [obj for obj in all_objects if obj.id not in excluded and obj.db_destination_id in rooms]
    offline = [obj for obj in all_objects
               if obj.is_typeclass('evennia.objects.objects.DefaultCharacter', exact=False)
               and getattr(obj.db.prelogout_location, 'id', None) in rooms]
    return {'offline': offline, 'rooms': rooms, 'anchor': anchors[0], 'exits': exits,
            'occupants': occupants, 'homes': homes, 'destinations': destinations}


def validated_scene(source):
    document = validate_map(source)
    try:
        document['items'] = validate_items(source.get('items', {}), document)
    except ValueError as error:
        raise InvalidEdit(str(error)) from error
    return document


def preview_map(document, mode='append', spawn=None):
    document = validated_scene(document)
    if mode not in ('append', 'replace'):
        raise InvalidEdit('导入模式必须是追加或替换。')
    result = {**summary(document), 'mode': mode}
    if mode == 'replace':
        plan = replacement_plan(document, spawn)
        result['replace'] = {'places': len(plan['rooms']), 'exits': len(plan['exits']),
                             'relocated_objects': len(plan['occupants']),
                             'updated_homes': len(plan['homes']), 'offline_locations': len(plan['offline'])}
    return result


def import_map(document, mode='append', spawn=None, *, items=None):
    document = validated_scene(document)
    if mode not in ('append', 'replace'):
        raise InvalidEdit('导入模式必须是追加或替换。')
    plan = replacement_plan(document, spawn) if mode == 'replace' else None
    previous_items = keyed_floor_items(plan['rooms']) if plan and document['items'] else {}
    nodes, created = {}, []
    # 保存对象引用和编号；异常回滚后同步 Evennia 的进程缓存。
    touched = {}
    if plan:
        for obj in [*plan['rooms'].values(), *plan['exits'], *plan['occupants'],
                    *plan['homes'], *plan['destinations'], *plan['offline']]:
            touched[obj.id] = obj
    try:
        with transaction.atomic():
            for node in document['nodes']:
                if plan and node['key'] == spawn:
                    obj = plan['anchor']
                    obj.key = node['name']
                    for name in ('parent', 'entry', 'position'):
                        obj.attributes.remove(name, category=CATEGORY)
                else:
                    obj = create_object('topology_editor.rooms.Area' if node['kind'] == 'area'
                                        else settings.BASE_ROOM_TYPECLASS, key=node['name'], nohome=True)
                    created.append(obj)
                nodes[node['key']] = obj
                obj.db.desc = node['description']
            for node in document['nodes']:
                obj = nodes[node['key']]
                obj.attributes.add('parent', nodes.get(node['parent']), category=CATEGORY)
                if node['kind'] == 'area':
                    obj.attributes.add('entry', nodes.get(node['entry']), category=CATEGORY)
            if plan:
                anchor = plan['anchor']
                # 管理操作使用 Evennia 对象属性接口，更新位置与 contents 缓存。
                for obj in plan['occupants']:
                    obj.location = anchor
                for obj in plan['homes']:
                    obj.home = anchor
                for obj in plan['destinations']:
                    obj.destination = anchor
                for obj in plan['offline']:
                    obj.db.prelogout_location = anchor
                # 清理旧出口后再删除空房间，避免 delete 自动搬移角色或残留通路。
                for obj in plan['exits']:
                    if not obj.delete():
                        raise InvalidEdit('游戏规则阻止删除旧出口，替换已回滚。')
                for obj in plan['rooms'].values():
                    if obj is not anchor and not obj.delete():
                        raise InvalidEdit('游戏规则阻止删除旧地点，替换已回滚。')
            specs = {n['key']: n for n in document['nodes']}
            for edge in document['connections']:
                target = specs[edge['target']]
                area = target['kind'] == 'area'
                obj = create_object(settings.BASE_EXIT_TYPECLASS, key=edge['name'],
                                    location=nodes[edge['source']],
                                    destination=nodes[target['entry'] if area else target['key']])
                created.append(obj)
                if area:
                    obj.attributes.add('area_target', nodes[target['key']], category=CATEGORY)
            for key, spec in document['items'].items():
                existing = previous_items.get(key)
                obj = place_item(key, spec, nodes[spec['room']], existing)
                if existing is None:
                    created.append(obj)
            if items:
                seed_items(document, items, nodes)
    except Exception:
        for obj in created:
            obj.flush_from_cache(force=True)
        if plan:
            Attribute.flush_instance_cache(force=True)
            for ident, obj in touched.items():
                obj.pk = ident
                obj.flush_from_cache(force=True)
            for ident, obj in touched.items():
                obj.pk = ident
                obj._is_deleted = False
                obj.refresh_from_db()
                obj.attributes.reset_cache()
                obj.contents_cache.init()
                obj.__class__.cache_instance(obj)
        raise
    return summary(document)
