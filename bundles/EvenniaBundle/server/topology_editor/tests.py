"""Regressions for item edits and adding fixtures to an already imported world."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from evennia.objects.models import ObjectDB
from evennia.utils.test_resources import EvenniaCommandTest, EvenniaTest

from item_interactions.actions import configured_actions, interact, set_actions
from item_interactions.commands import CmdInteract

from .bootstrap import at_server_start
from .schema import InvalidEdit
from .views import mutate


class ItemInteractionTests(EvenniaTest):
    def test_editor_validates_before_writing_and_preserves_game_state(self):
        edit = {'op': 'update_item', 'id': self.obj1.id, 'parent': self.room1.id,
                'name': '计步器', 'portable': True}
        mutate({**edit, 'actions': {'count': {'text': '前进一步。'}}})
        self.assertIn('累计 1 次', interact(self.char2, self.obj1, '计数'))
        with self.assertRaises(InvalidEdit):
            mutate({**edit, 'name': '无效改名', 'actions': {'toggle': {'on': '亮'}}})
        self.assertEqual(self.obj1.key, '计步器')
        mutate({**edit, 'actions': {'count': {'text': '又走了一步。'}}})
        mutate(edit)  # A client updating only the existing item fields.
        self.assertEqual(interact(self.char1, self.obj1, 'count'), '又走了一步。（累计 2 次）')
        self.obj1.location = self.char1
        self.assertEqual(interact(self.char2, self.obj1, 'count'), '你够不到这件物品。')
        self.obj1.location = self.room1
        mutate({**edit, 'actions': {}})
        self.assertEqual(configured_actions(self.obj1), {})

    def test_upgrade_seeds_items_without_reimporting_or_recreating_deleted_items(self):
        document = {'nodes': [{'key': 'campus', 'kind': 'room', 'name': self.room1.key,
                               'parent': None}]}
        config = {'document': document, 'mode': 'replace', 'spawn': 'campus'}
        item = {'room': 'campus', 'name': '站牌', 'portable': False,
                'description': '路线图', 'actions': {'read': {'text': '去学校'}}}
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'map.json'
            with self.settings(EMUVISTA_MAP_IMPORT_FILE=path), patch(
                    'topology_editor.bootstrap.import_map') as import_map:
                path.write_text(json.dumps(config))
                at_server_start()  # Old bundle stored only the map fingerprint.
                config['items'] = {'test.sign': item}
                path.write_text(json.dumps(config))
                at_server_start()
                sign = ObjectDB.objects.get(db_key='站牌')
                self.assertEqual(sign.location, self.room1)
                self.assertEqual(configured_actions(sign), item['actions'])
                sign.delete()
                at_server_start()
                self.assertFalse(ObjectDB.objects.filter(db_key='站牌').exists())
                import_map.assert_called_once()

    def test_single_file_append_export_and_replace(self):
        from .transfer import export_map, import_map, preview_map

        item = {'room': 'hall', 'name': '公告栏', 'description': '', 'portable': False,
                'actions': {'read': {'text': '下周开学。'}}}
        document = {'nodes': [{'key': 'hall', 'name': '大厅'}], 'connections': [],
                    'items': {'school.notice': item}}
        self.assertEqual(preview_map(document)['items'], 1)
        import_map(document)
        board = ObjectDB.objects.get(db_key='公告栏')
        exported = export_map()
        saved = exported['items']['school.notice']
        self.assertEqual(saved, {**item, 'room': f'room-{board.location.id}'})
        saved['actions']['read']['text'] = '今天开学。'
        with self.settings(DEFAULT_HOME=f'#{self.room1.id}', START_LOCATION=f'#{self.room1.id}'):
            import_map(exported, 'replace', f'room-{self.room1.id}')
        board = ObjectDB.objects.get(db_key='公告栏')
        self.assertEqual(board.location.key, '大厅')
        self.assertEqual(configured_actions(board)['read']['text'], '今天开学。')
        import_map(document)
        self.assertEqual(ObjectDB.objects.filter(db_key='公告栏').count(), 2)
        self.assertEqual(sum(i['name'] == '公告栏' for i in export_map()['items'].values()), 2)

    def test_invalid_item_rejected_before_import(self):
        from .transfer import import_map, preview_map

        document = {'nodes': [{'key': 'hall', 'name': '大厅'}], 'connections': [],
                    'items': {'bad': {'room': 'missing'}}}
        for operation in (import_map, preview_map):
            with self.assertRaises(InvalidEdit):
                operation(document)
        self.assertFalse(ObjectDB.objects.filter(db_key='大厅').exists())

    def test_startup_places_item_in_the_new_room(self):
        from .transfer import import_map

        document = {'nodes': [{'key': 'hall', 'name': '大厅'}], 'connections': []}
        items = {'school.notice': {'room': 'hall', 'name': '公告栏', 'description': '',
                                   'portable': False, 'actions': {}}}
        import_map(document, items=items)
        sign = ObjectDB.objects.get(db_key='公告栏')
        self.assertEqual(sign.location.key, '大厅')
        self.assertEqual(sign.attributes.get('map_item_key', category='topology_editor'), 'school.notice')


class ItemCommandTests(EvenniaCommandTest):
    def test_direct_verbs_and_full_command(self):
        self.obj1.key = '公交站牌'
        set_actions(self.obj1, {'read': {'text': '末班车八点。'},
                                'toggle': {'on': '亮起', 'off': '熄灭'},
                                'count': {'text': '已记录'}})
        for verb, result in [('阅读', '末班车八点。'), ('开关', '亮起'),
                             ('开关', '熄灭'), ('计数', '已记录（累计 1 次）')]:
            self.assertIn(verb, CmdInteract.aliases)
            self.call(CmdInteract(), ' 公交站牌', result, cmdstring=verb)
        self.call(CmdInteract(), ' 公交站牌 = 阅读', '末班车八点。')
        self.call(CmdInteract(), '', '用法：阅读 物品名', cmdstring='阅读')
        self.call(CmdInteract(), ' 公交站牌', '可用动作：阅读、开关、计数。', cmdstring='interact')
        set_actions(self.obj1, {})
        self.call(CmdInteract(), ' 公交站牌', '这件物品没有配置交互。', cmdstring='阅读')
