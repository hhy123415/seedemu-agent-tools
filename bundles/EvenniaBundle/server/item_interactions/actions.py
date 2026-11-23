"""Shared by game commands, server-side scripts and the world editor."""

CATEGORY = 'item_interactions'


def read(item, options):
    return options['text']


def toggle(item, options):
    enabled = not item.attributes.get('enabled', category=CATEGORY, default=False)
    item.attributes.add('enabled', enabled, category=CATEGORY)
    return options['on' if enabled else 'off']


def count(item, options):
    total = item.attributes.get('count', category=CATEGORY, default=0) + 1
    item.attributes.add('count', total, category=CATEGORY)
    return f"{options['text']}（累计 {total} 次）"


# Each entry supplies both the game handler and the fields the editor displays.
ACTIONS = {
    'read': ('阅读', {'text': '阅读内容'}, read),
    'toggle': ('开关', {'on': '开启时的反馈', 'off': '关闭时的反馈'}, toggle),
    'count': ('计数', {'text': '每次计数时的反馈'}, count),
}


def validate_actions(value):
    if not isinstance(value, dict) or value.keys() - ACTIONS.keys():
        raise ValueError('物品交互包含未知动作。')
    for key, options in value.items():
        label, fields, _ = ACTIONS[key]
        if not isinstance(options, dict) or options.keys() != fields.keys():
            raise ValueError(f'请填写“{label}”的全部交互字段。')
        for field, title in fields.items():
            text = options[field]
            if not isinstance(text, str) or not text.strip() or len(text) > 2000:
                raise ValueError(f'“{title}”须填写 1–2000 个字符。')
    return value


def configured_actions(item):
    stored = item.attributes.get('actions', category=CATEGORY, default={})
    return {key: dict(options) for key, options in stored.items()}


def set_actions(item, actions):
    item.attributes.add('actions', validate_actions(actions), category=CATEGORY)


def interact(actor, item, action=''):
    """List or execute one configured action for a nearby or carried item."""
    nearby = actor.location is not None and actor.location == item.location
    if item.location != actor and not nearby:
        return '你够不到这件物品。'
    if not item.access(actor, 'view', default=True) or not item.access(actor, 'use', default=True):
        return '你无法使用这件物品。'
    options = configured_actions(item)
    available = [key for key in ACTIONS if key in options]
    if not available:
        return '这件物品没有配置交互。'
    for key in available:
        label, _, handler = ACTIONS[key]
        if action in (key, label):
            return handler(item, options[key])
    labels = '、'.join(ACTIONS[key][0] for key in available)
    example = ACTIONS[available[0]][0]
    return f'可用动作：{labels}。例如：{example} {item.key}'
