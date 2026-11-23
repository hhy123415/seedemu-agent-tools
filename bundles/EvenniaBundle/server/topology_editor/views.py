"""Staff-only editing of rooms, placed items, exits and a containment tree."""
import hashlib
import json
import math
from pathlib import Path
from threading import RLock

from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.middleware.csrf import get_token
from django.template import engines
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_GET, require_POST
from evennia.objects.models import ObjectDB
from evennia.utils.ansi import strip_ansi
from evennia.utils.create import create_object

from .schema import InvalidEdit

ROOT = Path(__file__).parent
CATEGORY = 'topology_editor'
EDIT_LOCK = RLock()


def room_objects():
    return {obj.id: obj for obj in ObjectDB.objects.all().order_by('id')
            if obj.is_typeclass('evennia.objects.objects.DefaultRoom', exact=False)}


def item_objects(rooms):
    """Only objects placed directly in rooms; never expose characters or inventory."""
    return {obj.id: obj for obj in ObjectDB.objects.filter(db_location_id__in=rooms)
            if not any(obj.is_typeclass(path, exact=False) for path in (
                'evennia.objects.objects.DefaultRoom',
                'evennia.objects.objects.DefaultExit',
                'evennia.objects.objects.DefaultCharacter')) and not obj.has_account}


def item_for(value, rooms):
    obj = item_objects(rooms).get(object_id(value))
    if obj is None:
        raise InvalidEdit('物品不存在或已被角色拿走，请刷新。')
    return obj


def parent_id(room):
    value = room.attributes.get('parent', category=CATEGORY)
    return getattr(value, 'id', None)


def is_area(room):
    return room.is_typeclass('topology_editor.rooms.Area', exact=False)


def entry_id(room):
    return getattr(room.attributes.get('entry', category=CATEGORY), 'id', None)


def is_inside(child, area, rooms, parents=None):
    seen = set()
    current = child.id
    while current in rooms and current not in seen:
        seen.add(current)
        current = parents[current] if parents is not None else parent_id(rooms[current])
        if current == area.id:
            return True
    return False


def arrival(room, rooms):
    if not is_area(room):
        return room
    entry = rooms.get(entry_id(room))
    if not entry or is_area(entry) or not is_inside(entry, room, rooms):
        raise InvalidEdit('请先为该区域设置一个内部可站立地点作为入口。')
    return entry


def protected_ids():
    result = set()
    for key in ('DEFAULT_HOME', 'START_LOCATION'):
        try:
            result.add(int(str(getattr(settings, key, '')).lstrip('#')))
        except ValueError:
            pass
    return result


def snapshot():
    rooms = room_objects()
    nodes = []
    for room in rooms.values():
        parent = parent_id(room)
        stored_position = room.attributes.get('position', category=CATEGORY)
        # Evennia 将持久化列表包装为 SaverList，返回 JSON 前转换为普通列表。
        position = list(stored_position) if stored_position is not None else None
        nodes.append({'id': room.id, 'name': str(room.key),
                      'label': strip_ansi(str(room.key)),
                      'description': str(room.db.desc or ''),
                      'parent': parent if parent in rooms else None,
                      'position': position,
                      'kind': 'area' if is_area(room) else 'room',
                      'entry': entry_id(room),
                      'protected': room.id in protected_ids()})
    edges = [{'id': obj.id, 'name': str(obj.key), 'label': strip_ansi(str(obj.key)),
              'source': obj.db_location_id, 'target': obj.db_destination_id,
              'area_target': getattr(obj.attributes.get('area_target', category=CATEGORY), 'id', None)}
             for obj in ObjectDB.objects.filter(db_location_id__in=rooms,
                                                db_destination_id__in=rooms).order_by('id')
             if obj.is_typeclass('evennia.objects.objects.DefaultExit', exact=False)]
    items = []
    for obj in item_objects(rooms).values():
        point = obj.attributes.get('position', category=CATEGORY)
        items.append({'id': obj.id, 'name': str(obj.key), 'label': strip_ansi(str(obj.key)),
                      'description': str(obj.db.desc or ''), 'kind': 'item',
                      'parent': obj.db_location_id, 'position': list(point) if point is not None else None,
                      'portable': obj.locks.get('get') == 'get:all()', 'protected': False})
    payload = {'nodes': nodes, 'edges': edges, 'items': items}
    payload['revision'] = hashlib.sha256(json.dumps(payload, sort_keys=True,
                                                   ensure_ascii=False).encode()).hexdigest()
    return payload


def authorized(request):
    return request.user.is_authenticated and request.user.is_active and request.user.is_staff


@staff_member_required
@require_GET
@never_cache
def index(request):
    template = engines['django'].from_string((ROOT / 'editor.html').read_text())
    return HttpResponse(template.render({'csrf_token': get_token(request)}, request))


@staff_member_required
@require_GET
def javascript(request):
    return HttpResponse((ROOT / 'editor.js').read_text(), content_type='application/javascript')


@staff_member_required
@require_GET
def stylesheet(request):
    return HttpResponse((ROOT / 'editor.css').read_text(), content_type='text/css')


@require_GET
@never_cache
def data(request):
    if not authorized(request):
        return JsonResponse({'error': '请先使用管理员账号登录。'}, status=403)
    return JsonResponse(snapshot())


def object_id(value, nullable=False):
    if value is None and nullable:
        return None
    if type(value) is not int or value < 1:
        raise InvalidEdit('地点或出口编号无效。')
    return value


def room_for(value, rooms, nullable=False):
    ident = object_id(value, nullable)
    if ident is None:
        return None
    if ident not in rooms:
        raise InvalidEdit('地点不存在，请刷新地图。')
    return rooms[ident]


def text_field(body, key, limit, required=False):
    value = body.get(key, '')
    if not isinstance(value, str) or len(value) > limit:
        raise InvalidEdit(f'{key} 必须为文本，且不能超过 {limit} 个字符。')
    if required and not value.strip():
        raise InvalidEdit('名称不能为空。')
    return value.strip() if required else value


def check_parent(room, parent, rooms):
    seen = {room.id} if room else set()
    while parent:
        if parent.id in seen:
            raise InvalidEdit('不能把地点放进自身或它的下级地点。')
        seen.add(parent.id)
        parent = rooms.get(parent_id(parent))


def exit_for(value):
    obj = ObjectDB.objects.filter(id=object_id(value)).first()
    if not obj or not obj.is_typeclass('evennia.objects.objects.DefaultExit', exact=False):
        raise InvalidEdit('出口不存在。')
    return obj


def check_exit_name(name, source, exclude=None):
    for obj in source.contents:
        if obj.id == exclude or not obj.is_typeclass('evennia.objects.objects.DefaultExit', exact=False):
            continue
        if name.casefold() in {str(key).casefold() for key in [obj.key, *obj.aliases.all()]}:
            raise InvalidEdit('这个地点已经有同名出口或别名，请使用其他名称。')


def mutate(body):
    if body.get('op') == 'import_map':
        from .transfer import import_map
        return import_map(body.get('document'), body.get('mode', 'append'), body.get('spawn'))
    rooms = room_objects()
    op = body.get('op')
    if op in ('create_item', 'update_item'):
        obj = item_for(body.get('id'), rooms) if op == 'update_item' else None
        room = room_for(body.get('parent'), rooms)
        if is_area(room):
            raise InvalidEdit('物品必须放在教室等可站立地点中，不能放入区域。')
        name = text_field(body, 'name', 255, required=True)
        description = text_field(body, 'description', 20000)
        portable = body.get('portable', True)
        if type(portable) is not bool:
            raise InvalidEdit('可拾取选项必须为布尔值。')
        if obj is None:
            obj = create_object(settings.BASE_OBJECT_TYPECLASS, key=name, location=room, home=room)
        else:
            obj.key = name
            if obj.location != room:
                obj.location = room
                obj.home = room
                obj.attributes.remove('position', category=CATEGORY)
        obj.db.desc = description
        obj.locks.add('get:all()' if portable else 'get:false()')
        return obj.id
    if op == 'delete_item':
        obj = item_for(body.get('id'), rooms)
        if obj.contents:
            raise InvalidEdit('物品内部还有内容，不能删除。')
        if ObjectDB.objects.filter(Q(db_home_id=obj.id) | Q(db_destination_id=obj.id)).exists():
            raise InvalidEdit('物品仍被其他对象引用，不能删除。')
        if not obj.delete():
            raise InvalidEdit('游戏规则阻止了删除物品。')
        return None
    if op in ('create_room', 'update_room'):
        room = room_for(body.get('id'), rooms) if op == 'update_room' else None
        parent = room_for(body.get('parent'), rooms, nullable=True)
        name = text_field(body, 'name', 255, required=True)
        description = text_field(body, 'description', 20000)
        check_parent(room, parent, rooms)
        kind = body.get('kind', 'room')
        if kind not in ('room', 'area'):
            raise InvalidEdit('地点类型无效。')
        if room and (kind == 'area') != is_area(room):
            raise InvalidEdit('已有地点的类型不能直接切换，请新建后调整归属。')
        entry = room_for(body.get('entry'), rooms, nullable=True)
        if entry and (kind != 'area' or is_area(entry) or not room
                      or not is_inside(entry, room, rooms)):
            raise InvalidEdit('入口必须是该区域内部的可站立地点。')
        if room:
            parents = {ident: parent_id(obj) for ident, obj in rooms.items()}
            parents[room.id] = parent.id if parent else None
            for area in rooms.values():
                gate = rooms.get(entry_id(area))
                if gate and area != room and not is_inside(gate, area, rooms, parents):
                    raise InvalidEdit('移动后会使区域入口落到区域外，请先更改入口。')
            if is_area(room) and not entry:
                for obj in ObjectDB.objects.all():
                    if obj.attributes.get('area_target', category=CATEGORY) == room:
                        raise InvalidEdit('已有出口通向该区域，不能清空入口。')
        if room is None:
            typeclass = 'topology_editor.rooms.Area' if kind == 'area' else settings.BASE_ROOM_TYPECLASS
            room = create_object(typeclass, key=name)
        else:
            room.key = name
        old_parent = parent_id(room)
        room.db.desc = description
        room.attributes.add('parent', parent, category=CATEGORY)
        if is_area(room):
            room.attributes.add('entry', entry, category=CATEGORY)
            if entry:
                for obj in ObjectDB.objects.all():
                    if obj.attributes.get('area_target', category=CATEGORY) == room:
                        obj.destination = entry
        if old_parent != (parent.id if parent else None):
            room.attributes.remove('position', category=CATEGORY)
        return room.id
    if op == 'delete_room':
        room = room_for(body.get('id'), rooms)
        if room.id in protected_ids():
            raise InvalidEdit('默认出生地或回家地点不能在这里删除。')
        if any(entry_id(area) == room.id for area in rooms.values()):
            raise InvalidEdit('这个地点是区域入口，请先修改区域的入口。')
        if any(parent_id(child) == room.id for child in rooms.values()):
            raise InvalidEdit('请先移走或删除内部地点。')
        if ObjectDB.objects.filter(Q(db_location_id=room.id) | Q(db_destination_id=room.id)
                                   | Q(db_home_id=room.id)).exists():
            raise InvalidEdit('地点仍有角色、物品、出口或回家引用，请先处理这些内容。')
        if not room.delete():
            raise InvalidEdit('游戏规则阻止了删除此地点。')
        return None
    if op in ('create_exit', 'update_exit'):
        exit_obj = exit_for(body.get('id')) if op == 'update_exit' else None
        source = room_for(body.get('source'), rooms)
        target = room_for(body.get('target'), rooms)
        if is_area(source):
            raise InvalidEdit('出口起点必须是可站立地点，请选择区域入口或内部房间。')
        destination = arrival(target, rooms)
        name = text_field(body, 'name', 255, required=True)
        both = body.get('bidirectional', False)
        if type(both) is not bool:
            raise InvalidEdit('双向选项无效。')
        if exit_obj and both:
            raise InvalidEdit('已有出口请分别编辑两个方向。')
        check_exit_name(name, source, exit_obj.id if exit_obj else None)
        reverse = None
        if both:
            reverse = text_field(body, 'reverse_name', 255, required=True)
            check_exit_name(reverse, destination)
            if source == destination and name.casefold() == reverse.casefold():
                raise InvalidEdit('自环的两个出口不能同名。')
        if exit_obj:
            exit_obj.key = name
            exit_obj.location = source
            exit_obj.destination = destination
            # 出口名称就是游戏命令，清除旧的出口命令缓存。
            exit_obj.at_init()
        else:
            exit_obj = create_object(settings.BASE_EXIT_TYPECLASS, key=name,
                                     location=source, destination=destination)
            if both:
                create_object(settings.BASE_EXIT_TYPECLASS, key=reverse,
                              location=destination, destination=source)
        exit_obj.attributes.add('area_target', target if is_area(target) else None, category=CATEGORY)
        return exit_obj.id
    if op == 'delete_exit':
        if not exit_for(body.get('id')).delete():
            raise InvalidEdit('游戏规则阻止了删除此出口。')
        return None
    if op == 'layout':
        positions = body.get('positions')
        if not isinstance(positions, list) or len(positions) > 5000:
            raise InvalidEdit('布局数据无效。')
        checked = []
        for item in positions:
            if not isinstance(item, dict):
                raise InvalidEdit('布局数据无效。')
            room = room_for(item.get('id'), {**rooms, **item_objects(rooms)})
            point = [item.get('x'), item.get('y')]
            if any(type(v) not in (int, float) or not math.isfinite(v) or abs(v) > 100000
                   for v in point):
                raise InvalidEdit('坐标无效。')
            checked.append((room, point))
        for room, point in checked:
            room.attributes.add('position', point, category=CATEGORY)
        return None
    raise InvalidEdit('不支持的编辑操作。')


@require_POST
@csrf_protect
@never_cache
def edit(request):
    if not authorized(request):
        return JsonResponse({'error': '只有管理员可以编辑地图。'}, status=403)
    if len(request.body) > 1024 * 1024:
        return JsonResponse({'error': '请求内容过大。'}, status=400)
    try:
        body = json.loads(request.body)
        if not isinstance(body, dict):
            raise InvalidEdit('请求必须为 JSON 对象。')
        # 网页和游戏共用 Evennia Server；编辑前比较快照，避免覆盖其他窗口的修改。
        with EDIT_LOCK, transaction.atomic():
            current = snapshot()
            if body.get('revision') != current['revision']:
                return JsonResponse({'error': '地图已变化，请先刷新再编辑。'}, status=409)
            result = mutate(body)
            return JsonResponse({'result': result, **snapshot()})
    except (InvalidEdit, json.JSONDecodeError, UnicodeDecodeError, RecursionError) as error:
        return JsonResponse({'error': str(error)}, status=400)


@require_GET
@never_cache
def export_document(request):
    if not authorized(request):
        return JsonResponse({'error': '只有管理员可以导出地图。'}, status=403)
    from .transfer import export_map
    response = JsonResponse(export_map(), json_dumps_params={'ensure_ascii': False, 'indent': 2})
    response['Content-Disposition'] = 'attachment; filename="evennia-map.json"'
    return response


@require_POST
@csrf_protect
@never_cache
def preview_import(request):
    if not authorized(request):
        return JsonResponse({'error': '只有管理员可以导入地图。'}, status=403)
    if len(request.body) > 1024 * 1024:
        return JsonResponse({'error': '地图文件不能超过 1 MB。'}, status=400)
    from .transfer import preview_map
    try:
        body = json.loads(request.body)
        # 旧客户端直接提交地图；新客户端携带模式和安置地点。
        if isinstance(body, dict) and 'document' in body:
            return JsonResponse(preview_map(body['document'], body.get('mode', 'append'), body.get('spawn')))
        return JsonResponse(preview_map(body))
    except (InvalidEdit, json.JSONDecodeError, UnicodeDecodeError, RecursionError) as error:
        return JsonResponse({'error': str(error)}, status=400)
