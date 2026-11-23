"""Map validation shared by the compiler and the running editor (no Django required)."""
import re

FORMAT = 'emuvista.evennia.map'


class InvalidEdit(ValueError):
    pass


def validate_map(document):
    if not isinstance(document, dict):
        raise InvalidEdit('地图文件必须为 JSON 对象。')
    # 无版本的 school-map.json 是第一版学校示例格式，也支持直接导入。
    if ('format' in document or 'version' in document) and (
            document.get('format') != FORMAT or type(document.get('version')) is not int
            or document['version'] != 1):
        raise InvalidEdit('不支持的地图格式或版本。')
    raw_nodes, raw_edges = document.get('nodes'), document.get('connections')
    if not isinstance(raw_nodes, list) or not 1 <= len(raw_nodes) <= 1000:
        raise InvalidEdit('地图应包含 1–1000 个地点。')
    if not isinstance(raw_edges, list) or len(raw_edges) > 3000:
        raise InvalidEdit('connections 必须为列表，最多 3000 项。')
    nodes = {}

    def text(value, label, limit, required=False):
        if not isinstance(value, str) or len(value) > limit or (required and not value.strip()):
            raise InvalidEdit(f'{label} 必须为有效文本，最多 {limit} 个字符。')
        return value

    def ref(value, label, optional=False):
        if value is None and optional:
            return None
        if not isinstance(value, str) or value not in nodes:
            raise InvalidEdit(f'{label} 引用了不存在的地点。')
        return value

    for item in raw_nodes:
        if not isinstance(item, dict):
            raise InvalidEdit('每个地点必须为对象。')
        key = item.get('key')
        if not isinstance(key, str) or not re.fullmatch(r'[\w-]{1,100}', key):
            raise InvalidEdit('地点 key 必须是 1–100 个字母、数字、下划线或短横线。')
        if key in nodes:
            raise InvalidEdit(f'地点 key 重复：{key}')
        kind = item.get('kind', 'room')
        if kind not in ('room', 'area'):
            raise InvalidEdit(f'{key} 的类型必须为 room 或 area。')
        nodes[key] = {'key': key, 'name': text(item.get('name'), '名称', 255, True),
                      'description': text(item.get('description', ''), '描述', 20000),
                      'kind': kind,
                      'parent': item.get('parent'), 'entry': item.get('entry')}
    for node in nodes.values():
        ref(node['parent'], '所属地点', True)
        ref(node['entry'], '区域入口', True)
        seen, current = set(), node['key']
        while current is not None:
            if current in seen:
                raise InvalidEdit('地图中存在循环归属。')
            seen.add(current)
            current = nodes[current]['parent']
            ref(current, '所属地点', True)
    for node in nodes.values():
        entry = node['entry']
        if entry is not None:
            if node['kind'] != 'area' or nodes[entry]['kind'] != 'room':
                raise InvalidEdit('只有区域可以指定入口，入口必须为可站立地点。')
            current = nodes[entry]['parent']
            while current is not None and current != node['key']:
                current = nodes[current]['parent']
            if current is None:
                raise InvalidEdit('区域入口必须位于该区域内部。')
    edges = []
    for item in raw_edges:
        if not isinstance(item, dict):
            raise InvalidEdit('每个出口必须为对象。')
        source, target = ref(item.get('source'), '出口起点'), ref(item.get('target'), '出口终点')
        if nodes[source]['kind'] != 'room':
            raise InvalidEdit('出口起点必须为可站立地点。')
        if nodes[target]['kind'] == 'area' and nodes[target]['entry'] is None:
            raise InvalidEdit('出口指向的区域尚未设置入口。')
        edges.append({'source': source, 'target': target,
                      'name': text(item.get('name'), '出口名称', 255, True)})
        if 'reverse_name' in item:
            edges.append({'source': nodes[target]['entry'] if nodes[target]['kind'] == 'area' else target,
                          'target': source, 'name': text(item['reverse_name'], '返回出口名称', 255, True)})
    return {'format': FORMAT, 'version': 1, 'nodes': list(nodes.values()), 'connections': edges}


def summary(document):
    return {'places': len(document['nodes']),
            'areas': sum(n['kind'] == 'area' for n in document['nodes']),
            'exits': len(document['connections']),
            'roots': [n['name'] for n in document['nodes'] if n['parent'] is None]}


