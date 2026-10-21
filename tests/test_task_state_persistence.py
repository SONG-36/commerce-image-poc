"""G2 first-slice contracts. Anonymous temporary tasks only; no model calls."""

import ast
import copy
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import test_prepare_plan as fixtures
import file_ops
from persistence import task_state

web = fixtures.web


def plain_writer(path, value, exclusive=False):
    writer = file_ops.write_json_exclusive if exclusive else file_ops.write_json_atomic
    writer(path, value)


class TaskStatePersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = web.Store(self.root / '.runtime' / 'prepare-plan')
        self.identity = 'a' * 32
        self.folder = self.store.folder(self.identity)
        self.folder.mkdir(parents=True)
        self.state = {'id': self.identity, 'revision': 1, 'images': [], 'events': [],
                      'inputs': {'requirements': '匿名要求'}}

    def save_raw(self, state=None):
        task_state.write_snapshot_and_current(self.folder, state or self.state, writer=plain_writer)

    def test_raw_round_trip_leaves_business_state_and_input_untouched(self):
        state = {**self.state, 'revision': 7, 'confirmed': True,
                 'plan_confirmations': {'reference_001': {'unvalidated': 'raw payload'}}}
        before = copy.deepcopy(state)
        self.assertIsNone(task_state.write_snapshot_and_current(self.folder, state, writer=plain_writer))
        self.assertEqual(task_state.read_current(self.folder), before)
        self.assertEqual(task_state.read_snapshot(self.folder, 7), before)
        self.assertEqual(state, before)
        expected = (json.dumps(before, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
        self.assertEqual((self.folder / 'state.json').read_bytes(), expected)
        self.assertEqual((self.folder / 'versions/000007.json').read_bytes(), expected)

    def test_directory_snapshot_current_write_order_and_immutable_history(self):
        self.save_raw()
        old = (self.folder / 'state.json').read_bytes()
        updated = {**self.state, 'revision': 2}
        operations = []
        original_mkdir = Path.mkdir

        def mkdir(path, *args, **kwargs):
            operations.append(('mkdir', path.relative_to(self.folder).as_posix(), kwargs))
            return original_mkdir(path, *args, **kwargs)

        def write(path, value, exclusive=False):
            self.assertEqual((self.folder / 'state.json').read_bytes(), old)
            operations.append(('write', path.relative_to(self.folder).as_posix(), exclusive))
            plain_writer(path, value, exclusive)

        with patch.object(Path, 'mkdir', new=mkdir):
            task_state.write_snapshot_and_current(self.folder, updated, writer=write)
        self.assertEqual(operations, [('mkdir', 'versions', {'exist_ok': True}),
                                     ('write', 'versions/000002.json', True), ('write', 'state.json', False)])
        self.assertEqual((self.folder / 'versions/000001.json').read_bytes(), old)
        self.assertEqual(task_state.read_current(self.folder), updated)

    def test_duplicate_snapshot_stops_before_current_write(self):
        self.save_raw()
        old = {path: path.read_bytes() for path in self.folder.rglob('*.json')}
        attempted = []

        def write(path, value, exclusive=False):
            attempted.append(path.name)
            plain_writer(path, value, exclusive)

        with self.assertRaises(FileExistsError):
            task_state.write_snapshot_and_current(self.folder, {**self.state, 'extra': 'new'}, writer=write)
        self.assertEqual(attempted, ['000001.json'])
        self.assertEqual({path: path.read_bytes() for path in old}, old)

    def test_current_failure_retains_new_snapshot_and_old_current(self):
        self.save_raw()
        old = (self.folder / 'state.json').read_bytes()
        updated = {**self.state, 'revision': 2}
        error = PermissionError('simulated current write failure')

        def write(path, value, exclusive=False):
            if not exclusive:
                raise error
            plain_writer(path, value, exclusive)

        with self.assertRaises(PermissionError) as caught:
            task_state.write_snapshot_and_current(self.folder, updated, writer=write)
        self.assertIs(caught.exception, error)
        self.assertEqual(task_state.read_snapshot(self.folder, 2), updated)
        self.assertEqual((self.folder / 'state.json').read_bytes(), old)
        self.assertEqual(updated, {**self.state, 'revision': 2})

    def test_missing_parent_or_versions_file_is_not_repaired(self):
        absent = self.folder / 'absent'
        with self.assertRaises(FileNotFoundError):
            task_state.write_snapshot_and_current(absent, self.state, writer=plain_writer)
        self.assertFalse(absent.exists())
        (self.folder / 'versions').write_bytes(b'not a directory')
        with self.assertRaises(FileExistsError):
            self.save_raw()
        self.assertFalse((self.folder / 'state.json').exists())

    def test_read_missing_directory_corrupt_json_and_encoding_errors(self):
        (self.folder / 'versions').mkdir()
        for relative, reader in [('state.json', lambda: task_state.read_current(self.folder)),
                                 ('versions/000001.json', lambda: task_state.read_snapshot(self.folder, 1))]:
            with self.subTest(path=relative):
                path = self.folder / relative
                with self.assertRaises(task_state.MissingStateFile):
                    reader()
                path.mkdir()
                with self.assertRaises(task_state.MissingStateFile):
                    reader()
                path.rmdir()
                path.write_bytes(b'{broken')
                with self.assertRaises(json.JSONDecodeError):
                    reader()
                path.write_bytes(b'\xff')
                with self.assertRaises(UnicodeDecodeError):
                    reader()

    def test_symlinks_are_rejected_without_following_foreign_data(self):
        foreign = self.root / 'foreign'
        foreign.mkdir()
        (foreign / 'state.json').write_bytes(b'{}')
        (self.folder / 'state.json').symlink_to(foreign / 'state.json')
        (self.folder / 'versions').symlink_to(foreign, target_is_directory=True)
        with self.assertRaises(file_ops.ExportError):
            task_state.read_current(self.folder)
        with self.assertRaises(file_ops.ExportError):
            task_state.read_snapshot(self.folder, 1)
        with self.assertRaises(file_ops.ExportError):
            self.save_raw()
        self.assertEqual(list(foreign.iterdir()), [foreign / 'state.json'])
        self.assertEqual((foreign / 'state.json').read_bytes(), b'{}')

    def assert_problem(self, status, message, operation):
        with self.assertRaises(web.Problem) as caught:
            operation()
        self.assertEqual((caught.exception.status, str(caught.exception)), (status, message))

    def test_store_preserves_identifier_missing_and_revision_errors(self):
        for identity in ('../other', 'b' * 31, '/tmp/other', None):
            self.assert_problem(404, '无效的任务标识。', lambda: self.store.load(identity))
        self.assert_problem(404, '准备任务不存在，请重新加载资料。', lambda: self.store.load(self.identity))
        for revision in (None, 0, 2, '1'):
            self.assert_problem(409, '图片确认版本无效。', lambda: self.store.version(self.state, revision))
        self.assert_problem(409, '本任务的确认版本记录不存在。', lambda: self.store.version(self.state, 1))
        (self.folder / 'state.json').mkdir()
        self.assert_problem(404, '准备任务不存在，请重新加载资料。', lambda: self.store.load(self.identity))

    def test_store_keeps_payload_identity_image_path_and_snapshot_validation(self):
        for state, message in [({**self.state, 'id': 'b' * 32}, '任务标识与保存记录不一致。'),
                               ({**self.state, 'images': [{'file': '../foreign.png'}]}, '任务图片路径不在本任务允许范围内。')]:
            plain_writer(self.folder / 'state.json', state)
            self.assert_problem(409, message, lambda: self.store.load(self.identity))
        (self.folder / 'versions').mkdir()
        for changes in ({'id': 'b' * 32}, {'revision': 2}):
            plain_writer(self.folder / 'versions/000001.json', {**self.state, **changes})
            self.assert_problem(409, '历史计划记录与本任务不一致，已停止读取。',
                                lambda: self.store.version(self.state, 1))

    def test_store_only_maps_missing_file_precheck_not_reader_failures(self):
        self.save_raw()
        for operation in (lambda: self.store.load(self.identity), lambda: self.store.version(self.state, 1)):
            for error in (PermissionError('simulated'), FileNotFoundError('simulated read race')):
                with patch.object(web, 'read_json', side_effect=error), self.assertRaises(type(error)) as caught:
                    operation()
                self.assertIs(caught.exception, error)
        (self.folder / 'state.json').write_bytes(b'{broken')
        with self.assertRaises(json.JSONDecodeError):
            self.store.load(self.identity)

    def test_store_still_owns_mutation_and_caller_lock_on_partial_failure(self):
        self.save_raw()
        before = copy.deepcopy(self.state)
        old_current = (self.folder / 'state.json').read_bytes()
        original = web.write_json

        def write(path, value, exclusive=False):
            self.assertTrue(self.store.lock.locked())
            self.assertEqual(value['revision'], 2)
            self.assertEqual(value['events'][-1], {'at': 'fixed time', 'revision': 2, 'action': 'save'})
            if not exclusive:
                raise PermissionError('simulated current failure')
            original(path, value, exclusive=True)

        with self.store.lock, patch.object(web, 'now', return_value='fixed time'), \
                patch.object(web, 'write_json', side_effect=write), self.assertRaises(PermissionError):
            self.store.save(self.state, {'action': 'save'})
        self.assertFalse(self.store.lock.locked())
        self.assertEqual(self.state['revision'], before['revision'] + 1)
        self.assertEqual(task_state.read_snapshot(self.folder, 2), self.state)
        self.assertEqual((self.folder / 'state.json').read_bytes(), old_current)

    def test_characterized_task_files_and_write_order_match_before_extraction(self):
        # Captured from 0f796a2 BEFORE production changes: all input/state/snapshot
        # bytes and writer calls, including creation and current-task pointer order.
        expected = {'product_pack': 'e13dcdcaeac00b4c2197ad741c5c28de1ab814b988ee0beb73d917cb9e027b1d',
                    'quick_redesign': 'a86872917fd32bb1179e41d7f5bb4892696dcc51e59869ed0394211c34741a23'}
        for mode, fingerprint in expected.items():
            with self.subTest(mode=mode):
                root = self.root / mode
                store = web.Store(root)
                writes = []
                original = web.write_json

                def trace(path, value, exclusive=False):
                    writes.append([path.relative_to(root).as_posix(), exclusive])
                    return original(path, value, exclusive=exclusive)

                with patch.object(web, 'now', return_value='2026-01-01T00:00:00+00:00'), \
                        patch.object(web, 'uuid4', return_value=SimpleNamespace(hex='a' * 32)), \
                        patch.object(web, 'write_json', side_effect=trace):
                    state = store.create({'listing': 'anonymous listing', 'description': 'anonymous description',
                                          'requirements': 'anonymous requirements'},
                                         [('product', 'sample.png', fixtures.picture()),
                                          ('reference', 'style.png', fixtures.picture())], 'Anonymous task', mode=mode)
                    if mode == 'product_pack':
                        state['product'] = {key: 'candidate ' + key for key in web.PRODUCT_FIELDS}
                        state['references'] = {'reference_001': {key: 'candidate ' + key for key in web.REFERENCE_FIELDS}}
                        state['plans'] = {'reference_001': {key: 'candidate ' + key for key in web.PLAN_FIELDS}}
                        state['product_version'] = 1
                        state['reference_versions'] = {'reference_001': 1}
                        state['plan_context'] = {'reference_001': [1, 1]}
                        state['confirmed'] = True
                    store.save(state, {'action': 'anonymous_understand'})
                    if mode == 'product_pack':
                        web.materialize_confirmations(state)
                    store.save(state, {'action': 'anonymous_snapshot'})
                    self.assertEqual(store.load(state['id']), state)
                    self.assertEqual(store.version(state, 1)['revision'], 1)
                manifest = {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                            for p in sorted(root.rglob('*')) if p.is_file()}
                self.assertEqual(len(manifest), 8)
                actual = hashlib.sha256(json.dumps({'files': manifest, 'writes': writes},
                                                  ensure_ascii=False, sort_keys=True).encode()).hexdigest()
                self.assertEqual(actual, fingerprint)

    def test_persistence_dependency_direction_and_project_imports_are_acyclic(self):
        source = Path(web.__file__).parent
        tree = ast.parse(Path(task_state.__file__).read_text())
        self.assertEqual({node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}, {'file_ops'})
        self.assertFalse(any(isinstance(node, ast.Import) for node in ast.walk(tree)))
        graph = {}
        for path in source.rglob('*.py'):
            name = '.'.join(path.relative_to(source).with_suffix('').parts)
            if name.endswith('.__init__'):
                name = name.removesuffix('.__init__')
            graph[name] = set()
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.Import):
                    graph[name].update(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    graph[name].add(node.module)
                    graph[name].update(f'{node.module}.{alias.name}' for alias in node.names)

        def visit(name, chain):
            self.assertNotIn(name, chain, f'import cycle: {chain} -> {name}')
            for dependency in graph[name] & graph.keys():
                visit(dependency, chain + [name])

        for name in graph:
            visit(name, [])
        self.assertIn('persistence.task_state', graph['prepare_plan'])


if __name__ == '__main__':
    unittest.main()
