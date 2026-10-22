"""Review/version regressions using only temporary, anonymous image records."""

import base64
import copy
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import sys
import subprocess
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from file_ops import read_json, safe_path, sha256, write_json_atomic
from persistence.review_state import ReviewFiles
from image_workflow.review import (ImageScope, ReviewIO, apply_review, export_passed,
                                   image_bytes, review_transition, versions)
from image_workflow.review import validation


class ReviewPackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.scope = ImageScope('a' * 32, 3, 'reference_001')
        self.files = self.files_for(self.scope)
        self.ids = [f'20261021T000000Z-{number:032x}' for number in range(1, 4)]
        self.io = ReviewIO(new_id=lambda: SimpleNamespace(hex='f' * 32),
                           utc_now=lambda: datetime(2026, 10, 21, tzinfo=timezone.utc),
                           case_id=lambda: 'case-anonymous', sanitize=lambda value: value,
                           contains_private=lambda text: 'PRIVATE' in text)

    def files_for(self, scope):
        folder = safe_path(self.root, f'sessions/{scope.task_id}/generations/{scope.revision:06}/{scope.image_id}')
        return ReviewFiles(card_folder=lambda: folder,
                           run_folder=lambda identity: safe_path(folder, 'runs/' + identity))

    def seed(self, index=0, *, scope=None, version=None, **overrides):
        scope = scope or self.scope
        files = self.files_for(scope)
        folder = files.run_folder(self.ids[index])
        folder.mkdir(parents=True)
        data = png('pink' if index == 0 else 'blue')
        (folder / 'image.png').write_bytes(data)
        record = {'run_id': self.ids[index], 'session_id': scope.task_id, 'reference_id': scope.image_id,
                  'confirmed_revision': scope.revision, 'status': 'SUCCEEDED',
                  'version': version if version is not None else index + 1, 'started_at': f'time-{index}',
                  'output': {'validated': True, 'sha256': sha256(data)}, **overrides}
        write_json_atomic(folder / 'run.json', record)
        return folder, record

    def pointer(self, value):
        folder = self.files.card_folder()
        folder.mkdir(parents=True, exist_ok=True)
        write_json_atomic(folder / 'current.json', value)

    def snapshot(self):
        return {str(path.relative_to(self.root)): path.read_bytes() for path in self.root.rglob('*') if path.is_file()}

    def test_empty_queries_and_unpassed_export_are_read_only(self):
        before = self.snapshot()
        self.assertEqual(versions(self.scope, self.files), [])
        with self.assertRaisesRegex(ValueError, '所选图片版本不属于'):
            image_bytes(self.scope, self.files, self.ids[0])
        with self.assertRaisesRegex(ValueError, '尚无已 Pass'):
            self.export()
        self.assertEqual(self.snapshot(), before)

    def test_version_order_legacy_defaults_and_parent_auxiliary_metadata_are_preserved(self):
        first, record = self.seed(0)
        record.pop('version')
        write_json_atomic(first / 'run.json', record)
        self.seed(1, version=5, action='revise_image', feedback='Only this image', parent_run_id=self.ids[0],
                  auxiliary_reference={'purpose': 'product_appearance', 'sha256': 'anonymous-hash'})
        self.seed(2, status='FAILED', session_id='not-this-task')
        before = self.snapshot()
        rows = versions(self.scope, self.files)
        self.assertEqual([row['version'] for row in rows], [1, 5])
        self.assertEqual(rows[0]['action'], 'generate_image')
        self.assertEqual(rows[0]['feedback'], '')
        self.assertEqual(rows[1]['parent_run_id'], self.ids[0])
        self.assertEqual(rows[1]['auxiliary_reference']['purpose'], 'product_appearance')
        self.assertIn('/' + self.scope.task_id + '/', rows[1]['url'])
        self.assertEqual(self.snapshot(), before)

    def test_successful_run_scope_rejects_each_wrong_identity_without_writes(self):
        folder, original = self.seed()
        for key, value in [('session_id', 'b' * 32), ('reference_id', 'reference_002'),
                           ('confirmed_revision', 99), ('run_id', self.ids[1])]:
            with self.subTest(field=key):
                write_json_atomic(folder / 'run.json', {**original, key: value})
                before = self.snapshot()
                with self.assertRaisesRegex(ValueError, '图片记录与当前任务不一致'):
                    versions(self.scope, self.files)
                self.assertEqual(self.snapshot(), before)

    def test_missing_corrupt_and_incomplete_run_records_keep_native_behavior(self):
        folder, record = self.seed()
        (folder / 'run.json').unlink()
        self.assertEqual(versions(self.scope, self.files), [])
        (folder / 'run.json').write_text('{broken')
        with self.assertRaises(json.JSONDecodeError):
            versions(self.scope, self.files)
        record.pop('started_at')
        record['image_created_at'] = 'created'
        write_json_atomic(folder / 'run.json', record)
        # Preserve the old eager fallback lookup; this refactor does not repair
        # malformed legacy metadata or silently invent a timestamp.
        with self.assertRaises(KeyError):
            versions(self.scope, self.files)

    def test_image_bytes_checks_saved_integrity_and_preserves_files_on_error(self):
        folder, record = self.seed()
        data, metadata = image_bytes(self.scope, self.files, self.ids[0])
        self.assertEqual(data, (folder / 'image.png').read_bytes())
        self.assertEqual(metadata['run_id'], self.ids[0])
        write_json_atomic(folder / 'run.json', {**record, 'output': {'validated': False}})
        with self.assertRaisesRegex(ValueError, '图片文件与保存的记录不一致'):
            image_bytes(self.scope, self.files, self.ids[0])
        write_json_atomic(folder / 'run.json', record)
        (folder / 'image.png').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, '图片文件与保存的记录不一致'):
            image_bytes(self.scope, self.files, self.ids[0])
        (folder / 'image.png').unlink()
        with self.assertRaises(FileNotFoundError):
            image_bytes(self.scope, self.files, self.ids[0])

    def test_request_checks_precede_run_reads_and_pass_requires_actual_selection(self):
        self.pointer({'card_revision': 4})
        with patch.object(ReviewFiles, 'run_records', side_effect=AssertionError('Unexpected Run read')):
            for kind, revision, message in [('pass', 3, '图片状态已改变'), ('unknown', 4, '不支持的图片审核操作')]:
                with self.assertRaisesRegex(ValueError, message):
                    apply_review(self.scope, self.files, kind, self.ids[0], revision, io=self.io)
        self.seed(0)
        self.seed(1)
        self.pointer({'card_revision': 4, 'selected_run': self.ids[1]})
        with self.assertRaisesRegex(ValueError, '请先选择要审核'):
            apply_review(self.scope, self.files, 'pass', self.ids[0], 4, io=self.io)

    def test_transition_and_validation_are_pure_and_selected_passed_stay_independent(self):
        pointer = {'card_revision': 4, 'selected_run': self.ids[1], 'passed_run': self.ids[1],
                   'passed_at': 'earlier acceptance', 'last_successful_run': self.ids[1]}
        before = copy.deepcopy(pointer)
        with patch.object(Path, 'open', side_effect=AssertionError('Pure rules cannot read or write files')):
            validation.validate_review_request(pointer, 'select', 4)
            event, changed = review_transition(self.scope, pointer, {'version': 1}, 'select', self.ids[0], 4,
                                               event_id='event', case_id='case', created_at='time')
        self.assertEqual(pointer, before)
        self.assertEqual(changed['selected_run'], self.ids[0])
        self.assertEqual(changed['passed_run'], self.ids[1])
        self.assertEqual(changed['passed_at'], 'earlier acceptance')
        self.assertEqual(changed['card_revision'], 5)
        self.assertEqual(event['before_selected_run'], self.ids[1])
        self.assertEqual(event['after_passed_run'], self.ids[1])

    def test_select_and_explicit_pass_persist_exact_event_then_pointer(self):
        self.seed(0)
        self.seed(1)
        self.pointer({'card_revision': 4, 'selected_run': self.ids[1], 'passed_run': self.ids[1]})
        writes = []
        original_open, original_replace = Path.open, Path.replace

        def opened(path, mode='r', *args, **kwargs):
            if any(flag in mode for flag in ('x', 'w')):
                writes.append((path.name, mode))
            return original_open(path, mode, *args, **kwargs)

        def replaced(path, target):
            writes.append((path.name, 'replace:' + target.name))
            return original_replace(path, target)

        with patch.object(Path, 'open', opened), patch.object(Path, 'replace', replaced):
            event = apply_review(self.scope, self.files, 'select', self.ids[0], 4, io=self.io)
        self.assertEqual(writes, [('f' * 32 + '.json', 'x'), ('current.json.tmp', 'w'), ('current.json.tmp', 'replace:current.json')])
        folder = self.files.card_folder()
        self.assertEqual((folder / 'reviews' / ('f' * 32 + '.json')).read_bytes(),
                         (json.dumps(event, ensure_ascii=False, indent=2) + '\n').encode())
        self.assertEqual(read_json(folder / 'current.json')['passed_run'], self.ids[1])
        passed = apply_review(self.scope, self.files, 'pass', self.ids[0], 5,
                              io=replace(self.io, new_id=lambda: SimpleNamespace(hex='e' * 32)))
        self.assertEqual(passed['version'], 1)
        pointer = read_json(folder / 'current.json')
        self.assertEqual(pointer['selected_run'], self.ids[0])
        self.assertEqual(pointer['passed_run'], self.ids[0])
        self.assertEqual(pointer['card_revision'], 6)

    def test_duplicate_event_and_failed_pointer_replace_preserve_original_pointer(self):
        self.seed()
        self.pointer({'card_revision': 0, 'selected_run': self.ids[0]})
        before = (self.files.card_folder() / 'current.json').read_bytes()
        apply_review(self.scope, self.files, 'pass', self.ids[0], 0, io=self.io)
        pointer = self.files.card_folder() / 'current.json'
        after = pointer.read_bytes()
        with self.assertRaises(FileExistsError):
            apply_review(self.scope, self.files, 'select', self.ids[0], 1, io=self.io)
        self.assertEqual(pointer.read_bytes(), after)
        with patch.object(Path, 'replace', side_effect=OSError('offline replacement failure')):
            with self.assertRaisesRegex(OSError, 'replacement failure'):
                apply_review(self.scope, self.files, 'select', self.ids[0], 1,
                              io=replace(self.io, new_id=lambda: SimpleNamespace(hex='e' * 32)))
        self.assertEqual(pointer.read_bytes(), after)
        self.assertTrue((pointer.parent / 'current.json.tmp').exists())
        self.assertTrue((pointer.parent / 'reviews' / ('e' * 32 + '.json')).exists())
        self.assertNotEqual(before, after)

    def test_sanitizer_failure_retains_empty_event_without_pointer_update(self):
        self.seed()
        self.pointer({'selected_run': self.ids[0]})
        before = (self.files.card_folder() / 'current.json').read_bytes()
        def unavailable(value):
            raise RuntimeError('offline sanitizer failure')
        with self.assertRaisesRegex(RuntimeError, 'sanitizer failure'):
            apply_review(self.scope, self.files, 'pass', self.ids[0], 0, io=replace(self.io, sanitize=unavailable))
        self.assertEqual((self.files.card_folder() / 'current.json').read_bytes(), before)
        self.assertEqual((self.files.card_folder() / 'reviews' / ('f' * 32 + '.json')).read_bytes(), b'')

    def export(self, scopes=None, histories=None):
        scopes = scopes or [self.scope]
        states = {scope.image_id: [{'id': scope.task_id, 'revision': scope.revision}] for scope in scopes}
        return export_passed({'id': self.scope.task_id}, targets=lambda: [scope.image_id for scope in scopes],
            image_history=lambda target: iter((histories or states)[target]),
            files_for=lambda saved, target: self.files_for(ImageScope(saved['id'], saved['revision'], target)), io=self.io)

    def test_final_zip_uses_passed_not_selected_and_retains_sparse_image_number(self):
        self.seed(0)
        self.seed(1)
        self.pointer({'selected_run': self.ids[1], 'passed_run': self.ids[0]})
        before = self.snapshot()
        output, name = self.export()
        with zipfile.ZipFile(output) as archive:
            self.assertEqual(archive.namelist(), ['图片_01_V1.png'])
            self.assertEqual(archive.read(archive.namelist()[0]), png())
        self.assertIn(self.scope.task_id, name)
        self.assertEqual(self.snapshot(), before)
        second = ImageScope(self.scope.task_id, 3, 'reference_002')
        self.seed(0, scope=second)
        write_json_atomic(self.files_for(second).card_folder() / 'current.json', {'passed_run': self.ids[0]})
        self.pointer({'selected_run': self.ids[1]})
        output, _ = self.export([self.scope, second])
        with zipfile.ZipFile(output) as archive:
            self.assertEqual(archive.namelist(), ['图片_02_V1.png'])

    def test_delivery_finds_old_pass_but_never_falls_back_from_corrupt_new_pass(self):
        self.seed(0)
        self.pointer({'passed_run': self.ids[0]})
        current = ImageScope(self.scope.task_id, 4, self.scope.image_id)
        self.seed(1, scope=current)
        write_json_atomic(self.files_for(current).card_folder() / 'current.json', {'selected_run': self.ids[1]})
        history = {self.scope.image_id: [{'id': self.scope.task_id, 'revision': 4}, {'id': self.scope.task_id, 'revision': 3}]}
        output, _ = self.export(histories=history)
        with zipfile.ZipFile(output) as archive:
            self.assertEqual(archive.namelist(), ['图片_01_V1.png'])
        write_json_atomic(self.files_for(current).card_folder() / 'current.json', {'passed_run': self.ids[1]})
        (self.files_for(current).run_folder(self.ids[1]) / 'image.png').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, '图片文件与保存的记录不一致'):
            self.export(histories=history)

    def test_private_bytes_and_foreign_pass_are_not_exported_or_repaired(self):
        folder, record = self.seed()
        data = b'PRIVATE anonymous fixture'
        (folder / 'image.png').write_bytes(data)
        record['output']['sha256'] = sha256(data)
        write_json_atomic(folder / 'run.json', record)
        self.pointer({'passed_run': self.ids[0]})
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, '图片包含认证信息'):
            self.export()
        self.assertEqual(self.snapshot(), before)
        self.pointer({'passed_run': self.ids[1]})
        with self.assertRaisesRegex(ValueError, '所选图片版本不属于'):
            self.export()

    def test_symlink_paths_are_rejected_without_following_foreign_files(self):
        folder, _ = self.seed()
        other = self.root / 'foreign.json'
        other.write_text('{}')
        (folder / 'run.json').unlink()
        (folder / 'run.json').symlink_to(other)
        with self.assertRaises(ValueError):
            versions(self.scope, self.files)
        self.assertEqual(other.read_text(), '{}')

    def test_fresh_process_import_and_execution_need_no_web_sdk_or_generation(self):
        code = '''
import importlib.abc,runpy,sys,unittest
class Guard(importlib.abc.MetaPathFinder):
 def find_spec(self,fullname,*args):
  if fullname.split('.')[0] in {'flask','openai','prepare_plan','generate_plan_image','image_review','generate_image','quick_redesign','evidence'} or fullname.startswith(('image_workflow.generation','image_workflow.planning')):
   raise AssertionError('Forbidden Review dependency: '+fullname)
sys.meta_path.insert(0,Guard())
tests=runpy.run_path(sys.argv[1])['ReviewPackageTests']
result=unittest.TextTestRunner().run(unittest.TestSuite([
 tests('test_select_and_explicit_pass_persist_exact_event_then_pointer'),
 tests('test_final_zip_uses_passed_not_selected_and_retains_sparse_image_number')]))
sys.exit(not result.wasSuccessful())
'''
        result = subprocess.run([sys.executable, '-B', '-c', code, str(Path(__file__).resolve())],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)


def png(color='pink'):
    from PIL import Image
    output = io.BytesIO()
    Image.new('RGB', (24, 32), color).save(output, 'PNG')
    return output.getvalue()


class ReviewCoordinationTests(unittest.TestCase):
    def setUp(self):
        import test_generate_plan_image as fixtures
        self.fixtures = fixtures
        self.fx = fixtures.GenerationPageTests()
        self.fx.setUp()
        self.addCleanup(self.fx.doCleanups)
        self.generation = self.fx.app.extensions['generation_service']
        with self.fx.with_sdk():
            for target in ('reference_001', 'reference_002'):
                self.assertEqual(self.fx.post(target).status_code, 200)

    def review(self, target='reference_001', **overrides):
        card = next(card for card in self.fx.cards().json['cards'] if card['id'] == target)
        body = {'confirmed_revision': self.fx.state['revision'], 'card_revision': card['card_revision'],
                'action': 'pass', 'run_id': card['selected_run'], **overrides}
        return self.fx.app.test_client().post(f"/api/sessions/{self.fx.state['id']}/review/{target}",
                                              headers=self.fixtures.HEADERS, json=body)

    def test_review_uses_existing_image_lock_and_activity_without_a_second_registry(self):
        entered, release = threading.Event(), threading.Event()
        original_open = Path.open
        responses = []
        def blocked(path, mode='r', *args, **kwargs):
            if mode == 'x' and path.parent.name == 'reviews' and path.parent.parent.name == 'reference_001':
                entered.set()
                if not release.wait(5):
                    raise AssertionError('Offline review did not resume')
            return original_open(path, mode, *args, **kwargs)
        with patch.object(Path, 'open', blocked):
            thread = threading.Thread(target=lambda: responses.append(self.review()))
            thread.start()
            try:
                self.assertTrue(entered.wait(5))
                key = (self.fx.state['id'], self.fx.state['revision'], 'reference_001')
                self.assertIn(key, self.generation.active)
                self.assertTrue(self.generation.locks[key].locked())
                self.assertEqual(self.review().status_code, 409)
                self.assertEqual(self.fx.post('reference_001').status_code, 409)
                self.assertEqual(self.review('reference_002').status_code, 200)
                for endpoint in ('export-passed', 'export-experiment'):
                    response = self.fx.client.post(f"/api/sessions/{self.fx.state['id']}/{endpoint}", headers=self.fixtures.HEADERS)
                    self.assertEqual(response.status_code, 409)
                planning = self.fx.client.post(f"/api/sessions/{self.fx.state['id']}/action", headers=self.fixtures.HEADERS,
                    json={'action': 'replan', 'revision': self.fx.state['revision']})
                self.assertEqual(planning.status_code, 409)
            finally:
                release.set()
                thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(responses[0].status_code, 200)
        self.assertFalse(self.generation.active)
        self.assertTrue(all(not lock.locked() for lock in self.generation.locks.values()))
        self.assertEqual(len(self.fx.requests), 2)  # Setup Mock calls only.

    def test_http_scope_conflict_corrupt_record_and_missing_image_errors_remain_409(self):
        card = self.fx.cards().json['cards'][0]
        folder = self.generation.run_folder(self.fx.state['id'], self.fx.state['revision'], card['id'], card['selected_run'])
        response = self.review(card_revision=card['card_revision'] - 1)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json['error'], '图片状态已改变，请刷新后再操作。')
        response = self.review(run_id='20261021T000000Z-' + 'f' * 32)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json['error'], '所选图片版本不属于本任务、本张图片或当前确认计划。')
        original = (folder / 'run.json').read_bytes()
        # Freeze a valid POST before corrupting its underlying record; GET card
        # assembly also correctly propagates corrupt data rather than repairing it.
        url = f"/api/sessions/{self.fx.state['id']}/review/reference_001"
        body = {'confirmed_revision': self.fx.state['revision'], 'card_revision': card['card_revision'],
                'action': 'pass', 'run_id': card['selected_run']}
        (folder / 'run.json').write_text('{broken')
        response = self.fx.client.post(url, headers=self.fixtures.HEADERS, json=body)
        self.assertEqual(response.status_code, 409)
        self.assertIn('Expecting property name', response.json['error'])
        (folder / 'run.json').write_bytes(original)
        (folder / 'image.png').unlink()
        response = self.fx.client.post(url, headers=self.fixtures.HEADERS, json=body)
        self.assertEqual(response.status_code, 409)
        self.assertFalse(self.generation.active)
        self.assertFalse((folder.parent.parent / 'reviews').exists())
        self.assertEqual(len(self.fx.requests), 2)


def compatibility_fingerprints(*, details=False):
    """Original 289eebe behavior, captured before Review extraction.

    Compare stable files, events, pointers, exceptions, lock cleanup, write order
    and ZIP members/bytes. ZIP timestamps are not business state or compared.
    """
    from infrastructure import evidence
    from image_workflow.tasks import review as legacy
    from image_workflow.tasks.generation_runtime import GenerationService

    cases = {}
    scenarios = ('empty', 'versions', 'legacy_versions', 'select', 'pass', 'pass_unselected', 'stale',
                 'invalid_action', 'foreign_task', 'foreign_image', 'foreign_revision', 'foreign_run',
                 'missing_record', 'corrupt_record', 'missing_image', 'changed_image', 'invalid_output',
                 'event_exists', 'sanitize_error', 'replace_error', 'busy', 'export', 'export_sparse',
                 'export_no_pass', 'export_history', 'export_bad_pass', 'export_private')
    for scenario in scenarios:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            state = {'id': 'a' * 32, 'revision': 3,
                     'images': [{'id': name, 'role': 'reference'} for name in ('reference_001', 'reference_002')]}
            older = {**state, 'revision': 1}
            store = SimpleNamespace(folder=lambda identity: safe_path(root, 'sessions/' + identity),
                                    case_id=lambda state: 'case-anonymous',
                                    image_history=lambda state, target: iter([state, older]))
            generation = GenerationService(store)
            target = 'reference_001'
            identities = [f'20261021T000000Z-{index:032x}' for index in (1, 2, 3)]

            def seed(saved, image, identity, number, color):
                folder = generation.run_folder(saved['id'], saved['revision'], image, identity)
                folder.mkdir(parents=True)
                data = png(color)
                (folder / 'image.png').write_bytes(data)
                record = {'run_id': identity, 'session_id': saved['id'], 'reference_id': image,
                          'confirmed_revision': saved['revision'], 'status': 'SUCCEEDED', 'version': number,
                          'started_at': f'fixed-{number}', 'finished_at': f'fixed-{number}',
                          'action': 'generate_image' if number == 1 else 'revise_image',
                          'feedback': '' if number == 1 else 'Only current image',
                          'parent_run_id': None if number == 1 else identities[0],
                          'output': {'validated': True, 'sha256': sha256(data)}}
                write_json_atomic(folder / 'run.json', record)
                return folder

            first = second = None
            if scenario != 'empty':
                first = seed(state, target, identities[0], 1, 'pink')
                second = seed(state, target, identities[1], 2, 'blue')
                write_json_atomic(first.parent.parent / 'current.json', {
                    'latest_run': identities[1], 'selected_run': identities[1], 'last_successful_run': identities[1],
                    'passed_run': identities[0], 'card_revision': 4})
            if scenario == 'legacy_versions':
                record = read_json(first / 'run.json')
                record.pop('version')
                record.pop('action')
                record.pop('parent_run_id')
                record.pop('feedback')
                write_json_atomic(first / 'run.json', record)
            if scenario in ('foreign_task', 'foreign_image', 'foreign_revision', 'foreign_run', 'invalid_output'):
                record = read_json(second / 'run.json')
                field, value = {'foreign_task': ('session_id', 'b' * 32),
                                'foreign_image': ('reference_id', 'reference_002'),
                                'foreign_revision': ('confirmed_revision', 99),
                                'foreign_run': ('run_id', identities[2]),
                                'invalid_output': ('output', {'validated': False})}[scenario]
                record[field] = value
                write_json_atomic(second / 'run.json', record)
            if scenario == 'missing_record': (second / 'run.json').unlink()
            if scenario == 'corrupt_record': (second / 'run.json').write_text('{broken')
            if scenario == 'missing_image': (second / 'image.png').unlink()
            if scenario == 'changed_image': (second / 'image.png').write_bytes(b'changed anonymous bytes')
            if scenario == 'event_exists':
                events = first.parent.parent / 'reviews'
                events.mkdir()
                (events / ('f' * 32 + '.json')).write_text('existing immutable event')
            if scenario == 'export_sparse':
                other = seed(state, 'reference_002', identities[0], 1, 'green')
                write_json_atomic(other.parent.parent / 'current.json', {'passed_run': identities[0]})
            if scenario in ('export_sparse', 'export_no_pass', 'export_history'):
                pointer = read_json(first.parent.parent / 'current.json')
                pointer.pop('passed_run')
                write_json_atomic(first.parent.parent / 'current.json', pointer)
            if scenario == 'export_history':
                old = seed(older, target, identities[2], 3, 'green')
                write_json_atomic(old.parent.parent / 'current.json', {'passed_run': identities[2]})
            if scenario == 'export_bad_pass':
                pointer = read_json(first.parent.parent / 'current.json')
                pointer['passed_run'] = identities[2]
                write_json_atomic(first.parent.parent / 'current.json', pointer)
            if scenario == 'export_private':
                data = b'OPENAI_API_KEY=offline-placeholder'
                (first / 'image.png').write_bytes(data)
                record = read_json(first / 'run.json')
                record['output']['sha256'] = sha256(data)
                write_json_atomic(first / 'run.json', record)
            if scenario == 'busy':
                lock = generation.locks.setdefault((state['id'], 3, target), threading.Lock())
                lock.acquire()
            original_open, original_replace = Path.open, Path.replace
            writes = []

            def opened(path, mode='r', *args, **kwargs):
                if path.is_relative_to(root) and any(flag in mode for flag in ('w', 'a', 'x', '+')):
                    writes.append(['open', str(path.relative_to(root)), mode])
                return original_open(path, mode, *args, **kwargs)

            def replaced(path, destination):
                writes.append(['replace', str(path.relative_to(root)), str(destination.relative_to(root))])
                if scenario == 'replace_error':
                    raise OSError('offline replace failure')
                return original_replace(path, destination)

            def sanitize(value):
                raise RuntimeError('offline sanitizer failure')

            try:
                with patch.object(Path, 'open', opened), patch.object(Path, 'replace', replaced), \
                        patch.object(legacy, 'uuid4', return_value=SimpleNamespace(hex='f' * 32)), \
                        patch.object(legacy, 'datetime', SimpleNamespace(now=lambda tz: datetime(2026, 10, 21, tzinfo=timezone.utc))), \
                        patch.object(legacy, 'clean_record', side_effect=sanitize) if scenario == 'sanitize_error' else patch.object(legacy, 'clean_record', wraps=legacy.clean_record):
                    if scenario in ('empty', 'versions', 'legacy_versions'):
                        outcome = {'versions': legacy.versions(generation, state, target)}
                    elif scenario.startswith('export'):
                        output, filename = legacy.export_passed(generation, state)
                        with zipfile.ZipFile(output) as archive:
                            outcome = {'filename': filename, 'members': [(name, archive.read(name)) for name in archive.namelist()]}
                    else:
                        event = legacy.review(generation, state, target,
                            'unknown' if scenario == 'invalid_action' else 'pass' if scenario in ('pass', 'pass_unselected') else 'select',
                            identities[0] if scenario in ('select', 'pass_unselected') else identities[1],
                            3 if scenario == 'stale' else 4)
                        outcome = {'event': event}
            except Exception as error:
                outcome = {'type': type(error).__name__, 'message': str(error)}
            finally:
                if scenario == 'busy':lock.release()
            assert not generation.active, scenario
            assert all(not lock.locked() for lock in generation.locks.values()), scenario
            files = {}
            for path in sorted(root.rglob('*')):
                if path.is_file():
                    files[str(path.relative_to(root))] = path.read_text() if path.suffix == '.json' else path.read_bytes()
            payload = json.dumps({'outcome': outcome, 'writes': writes, 'files': files}, ensure_ascii=False,
                                 sort_keys=True, default=lambda value: {'bytes_b64': base64.b64encode(value).decode()})
            payload = payload.replace(str(root), '<ROOT>')
            cases[scenario] = json.loads(payload) if details else hashlib.sha256(payload.encode()).hexdigest()
    return cases


class ReviewCompatibilityTests(unittest.TestCase):
    def test_legacy_versions_events_pointers_errors_and_final_zip_are_equivalent(self):
        self.assertEqual(compatibility_fingerprints(), LEGACY_GOLDEN)


LEGACY_GOLDEN = {
    'empty': 'df610d31bc2743a3ff7ec2aae3783e67ced27108b502168554e38ee0177c5250',
    'versions': '89a6a7d8e83034952cd320efa13149b00695bbbf045991db8d779430dad14638',
    'legacy_versions': '4fa83d1fc3f9132def94510fc22de3d1bdaa9640b1eec0dd156cf4e370364484',
    'select': '4b1ab5cdae249e71774ba9bebe33ba0b1faf16bd1c0c72a897461229ec2c9868',
    'pass': 'b98b8acc468d8fb02538c52b23c0b3629070426172015c160b5cf164c5f95c4c',
    'pass_unselected': 'f2fbe8fa60b4ae6c53c93c09858b469da759452330005b14f7c512ae61e54b34',
    'stale': 'd7c08eb0f84b52d0e08941a15d81d8b97ec711258b7bbd422e7bb0e59f915c6e',
    'invalid_action': '060895d63f895e13178c8104a221b2fd85e31770726cc4f10e76d3aec902f342',
    'foreign_task': '5f30a084c29005cd330d9d0205c80389cc65b8144b6b553f4f2c50adece856da',
    'foreign_image': 'e579ab816e81bf161d0b33b71b1b444bb1f6a5429d204952f250ee51d419065b',
    'foreign_revision': 'f10cc7dafcefa36dcab1a8fd80a0de7a9dab90fd0d3cb56ddea020b22fd44355',
    'foreign_run': '879505648c45f8bbb09ba4f17e9d8db07e4cb22986f29691ddba172f92b61d1e',
    'missing_record': '56af7d6cc1925a87e3f002b17db759422ce3c46a6640bf963a2d227a90c6f08f',
    'corrupt_record': '4bc797b7c65a6cc428faabc6950e3a54ede480fa6b06de818bc294ca7e23c278',
    'missing_image': 'de9ace85c50b9d8f8f930b77a655a87fffdb7843869f092188ea4b8b74dc5067',
    'changed_image': '750fc2ca34001e6f48a18a3754875b048e8e8a1bfe44ec7a0f266abb38286cc4',
    'invalid_output': '1b8810ca98a48b47458fc2e86b4c0263246d9ea102105ca4d9a7adfe964f8c2c',
    'event_exists': '6ff94a48d027b4bd90100049c706188105ac709c30b49209b221277ec0726aa5',
    'sanitize_error': '5b38c541e8001c7e3040364a30fc45cbe2b959e79bfe8917b4f13955216c588c',
    'replace_error': '4b57d32a0f06ded4f7c907242e19c6c86f5e595bda5ec1f875856820fffcc834',
    'busy': '8b17aa1b7cad57964a0fe1d5c65482e2655ab63b67b72c811e892b4b495e72bf',
    'export': 'aed750a0ea768918126e5a2741c6347495d52beec910f7821e1dd1e4815d2112',
    'export_sparse': 'fc20e68e22f52b61f9a593258a7c14d18cd1be9d32643ddb9b80326e40248d7a',
    'export_no_pass': '4435ebf68854e85f5761c581e06845553eb77a206ea57f62310f160d0e6410ef',
    'export_history': '971f75c05fdc0fef43ed7e7d86b6f3ad77a890cbd681ddc799df7e529d6d0176',
    'export_bad_pass': '12106e7b096bf250727c617415c833f5a1c81fcce0068e08501478c51f56749c',
    'export_private': 'f002610b7d25d8923ad20843c1bf43f36191864e401d5acabb5878fb1f7bf0b0',
}


if __name__ == '__main__':
    unittest.main()
