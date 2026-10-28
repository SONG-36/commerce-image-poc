"""Task rules/use cases without Flask, SDK or real runtime; plus legacy fingerprints."""

import copy
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from file_ops import read_json, write_json_atomic, write_json_exclusive
from image_workflow import Problem
from image_workflow.planning.validation import PRODUCT_FIELDS, REFERENCE_FIELDS, PLAN_FIELDS
from image_workflow.tasks import rules
from image_workflow.tasks.queries import TaskQueries, image_state, version
from image_workflow.tasks.service import TaskApplication, create_task, save_task
from image_workflow.tasks.storage import TaskFiles


STAMP = '2026-01-01T00:00:00+00:00'
TARGETS = ['reference_001', 'reference_002']


def candidate(fields, label):
    return {key: label + ' ' + key for key in fields}


def initial_state():
    return {'id': 'a' * 32, 'revision': 1, 'title': 'Anonymous', 'created_at': STAMP,
            'mode': 'product_pack', 'inputs': {'listing': 'anonymous', 'description': '', 'requirements': 'anonymous'},
            'images': [{'id': name, 'role': 'reference', 'file': 'inputs/' + name + '.png',
                        'name': name, 'mime': 'image/png'} for name in TARGETS],
            'product': None, 'references': {}, 'plans': {}, 'product_version': 0, 'reference_versions': {},
            'plan_context': {}, 'corrections': {'product': [], 'references': {}}, 'events': [], 'confirmed': False}


def initial_result():
    return {'product': candidate(PRODUCT_FIELDS, 'product'),
            'references': {name: candidate(REFERENCE_FIELDS, name) for name in TARGETS},
            'plans': {name: candidate(PLAN_FIELDS, name) for name in TARGETS}}


class MemoryTask:
    """Small Task port for use-case tests; not a second production store."""
    def __init__(self, root):
        self.root = Path(root)
        self.state = initial_state()
        self.snapshots = {1: copy.deepcopy(self.state)}
        self.lock = threading.Lock()
        self.planning = {}
        self.trace = []
        self.fail_persist = False

    def load(self, identity):
        if identity != self.state['id']:
            raise Problem('missing', 404)
        return copy.deepcopy(self.state)

    def persist(self, state):
        self.trace.append('persist')
        if self.fail_persist:
            raise OSError('offline persist failure')
        self.state = copy.deepcopy(state)
        self.snapshots[state['revision']] = copy.deepcopy(state)

    def save(self, state, event):
        save_task(self, state, event, clock=lambda: STAMP)

    def folder(self, identity):
        return self.root / identity

    def case_id(self, state):
        return 'case-anonymous'

    def read_snapshot(self, identity, revision):
        return copy.deepcopy(self.snapshots[revision])

    def version(self, state, revision):
        return version(self, state, revision)

    def image_state(self, state, target):
        return image_state(self, state, target)


class ImagePeer:
    def __init__(self):
        self.guard = threading.Lock()
        self.active = set()

    def targets(self, state):
        return [image['id'] for image in state['images'] if image['role'] == 'reference']

    def card(self, state, target):
        return {'id': target, 'confirmed_revision': state['revision'], 'status': 'NOT_STARTED',
                'versions': [], 'passed_run': None, 'run_id': None, 'request_uncertain': False}


class TaskApplicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = MemoryTask(self.temp.name)
        self.images = ImagePeer()
        self.calls, self.applied = [], []
        self.app = TaskApplication(self.store, self.images, planner=self.plan, clock=lambda: STAMP, writer=self.write)

    def plan(self, state, action, target, feedback):
        self.assertTrue(self.store.lock.locked())
        self.assertFalse(self.images.guard.locked())
        self.calls.append((action, target, feedback))
        return initial_result(), 'b' * 32

    def write(self, path, value, exclusive=False):
        self.assertTrue(self.store.lock.locked())
        self.store.trace.append('applied')
        self.applied.append((path, copy.deepcopy(value), exclusive))

    def act(self, action, target=None, feedback='', **extra):
        body = {'action': action, 'target': target, 'feedback': feedback,
                'revision': self.store.state['revision'], **extra}
        def read():
            self.assertTrue(self.store.lock.locked())
            return body
        return self.app.action(self.store.state['id'], read)

    def ready(self):
        return self.act('understand')

    def test_application_runs_planning_then_state_then_applied_with_the_original_lock(self):
        state = self.ready()
        self.assertEqual(state['revision'], 2)
        self.assertEqual(state['product_version'], 1)
        self.assertEqual(self.store.trace, ['persist', 'applied'])
        path, applied, exclusive = self.applied[0]
        self.assertEqual(path.name, 'applied.json')
        self.assertEqual(applied, {'revision': 2, 'parent_revision': 1, 'run_id': 'b' * 32,
                         'case_id': 'case-anonymous', 'version_file': 'versions/000002.json', 'at': STAMP})
        self.assertTrue(exclusive)
        self.assertFalse(self.store.lock.locked())

    def test_confirmation_rules_are_offline_and_only_target_plan_is_invalidated(self):
        state = self.ready()
        with patch.object(Path, 'open', side_effect=AssertionError('Pure rules cannot open files')):
            event = rules.confirm_plan(state, TARGETS[0], {}, clock=lambda: STAMP)
            self.assertEqual(event['target'], TARGETS[0])
            self.assertEqual(state['plan_confirmations'][TARGETS[0]]['revision'], 3)
            self.store.save(state, event)
            self.assertTrue(rules.plan_status(state, TARGETS[0])['confirmed'])
            other = copy.deepcopy(state['plans'][TARGETS[1]])
            changed = {'plan': candidate(PLAN_FIELDS, 'changed')}
            rules.apply_planning_result(state, 'plan', TARGETS[1], 'only second', changed, 'call')
            self.assertTrue(rules.plan_status(state, TARGETS[0])['confirmed'])
            self.assertFalse(rules.plan_status(state, TARGETS[1])['confirmed'])
            self.assertNotEqual(state['plans'][TARGETS[1]], other)

    def test_product_and_reference_corrections_preserve_plans_and_invalidate_correct_scope(self):
        for kind, target in [('product', None), ('reference', TARGETS[0])]:
            state = initial_state()
            rules.apply_planning_result(state, 'understand', None, '', initial_result(), 'call')
            state['revision'] = 2
            for name in TARGETS:
                event = rules.confirm_plan(state, name, {}, clock=lambda: STAMP)
                self.store.save(state, event)
            before = copy.deepcopy(state['plans'])
            result = {'product': candidate(PRODUCT_FIELDS, 'changed')} if kind == 'product' else {'reference': candidate(REFERENCE_FIELDS, 'changed')}
            rules.apply_planning_result(state, kind, target, 'feedback', result, 'next')
            self.assertEqual(state['plans'], before)
            self.assertEqual(rules.stale_ids(state), TARGETS if kind == 'product' else [TARGETS[0]])

    def test_confirmation_noop_stale_revision_and_existing_snapshot_binding(self):
        self.ready()
        first = self.act('confirm', TARGETS[0])
        bound = first['plan_confirmations'][TARGETS[0]]['revision']
        count = len(self.applied)
        same = self.act('confirm', TARGETS[0])
        self.assertEqual(first, same)
        self.assertEqual(len(self.applied), count)
        latest = self.act('confirm', TARGETS[1])
        self.assertEqual(self.store.image_state(latest, TARGETS[0])['revision'], bound)
        self.assertEqual(len(self.calls), 1)
        with self.assertRaises(Problem):
            self.act('confirm', TARGETS[0], plan_version=999)
        self.assertFalse(self.store.lock.locked())

    def test_active_image_and_busy_store_reject_before_reading_command(self):
        def unreadable():
            raise AssertionError('Command must not be parsed')
        self.images.active.add((self.store.state['id'], 1, TARGETS[0]))
        with self.assertRaises(Problem) as caught:
            self.app.action(self.store.state['id'], unreadable)
        self.assertEqual(caught.exception.status, 409)
        self.assertFalse(self.store.lock.locked())
        self.images.active.clear()
        with self.store.lock, self.assertRaises(Problem):
            self.app.action(self.store.state['id'], unreadable)
        self.assertEqual(self.calls, [])

    def test_planner_and_persistence_failures_never_write_applied_or_keep_lock(self):
        before = copy.deepcopy(self.store.state)
        with patch.object(self.app, 'planner', side_effect=Problem('offline failure', 502)):
            with self.assertRaises(Problem):
                self.act('understand')
        self.assertEqual(self.store.state, before)
        self.assertEqual(self.applied, [])
        self.assertFalse(self.store.lock.locked())
        self.store.fail_persist = True
        with self.assertRaisesRegex(OSError, 'persist failure'):
            self.act('understand')
        self.assertEqual(self.store.state, before)
        self.assertEqual(self.applied, [])
        self.assertFalse(self.store.lock.locked())

    def test_queries_are_read_only_and_legacy_confirmation_is_not_materialized(self):
        state = self.ready()
        state['confirmed'] = True
        state.pop('plan_confirmations')
        state.pop('plan_versions')
        before = copy.deepcopy(state)
        queries = TaskQueries(self.store, self.images, auxiliary_purposes={}, auxiliary_max_bytes=20, quick_sizes=('1024x1536',))
        result = queries.public(state)
        self.assertTrue(all(item['confirmed'] for item in result['plan_status'].values()))
        self.assertTrue(all(item['legacy'] for item in result['plan_status'].values()))
        self.assertEqual(state, before)
        self.assertNotIn('url', state['images'][0])
        self.assertIn('url', result['images'][0])

    def test_input_readers_stay_inside_existing_lock_and_copy_validation_order(self):
        calls = []
        def form():
            self.assertTrue(self.store.lock.locked())
            calls.append('form')
            return {'title': 'New', 'listing': '', 'description': '', 'requirements': '', 'mode': 'product_pack'}
        def uploads():
            self.assertTrue(self.store.lock.locked())
            calls.append('uploads')
            return []
        self.store.create = lambda *args, **kwargs: calls.append('create') or initial_state()
        self.app.save_inputs(form, uploads)
        self.assertEqual(calls, ['form', 'uploads', 'create'])
        self.assertFalse(self.store.lock.locked())

    def test_creation_uses_file_boundary_for_both_modes_and_keeps_snapshot_order(self):
        from PIL import Image
        data = io.BytesIO()
        Image.new('RGB', (12, 16), 'pink').save(data, 'PNG')
        for mode in ('product_pack', 'quick_redesign'):
            events = []
            def writer(path, value, exclusive=False):
                events.append((path.name, exclusive))
                (write_json_exclusive if exclusive else write_json_atomic)(path, value)
            files = TaskFiles(Path(self.temp.name) / mode, reader=read_json, writer=writer)
            files.save = lambda state, event: save_task(files, state, event, clock=lambda: STAMP)
            state = create_task(files, {'listing': '', 'description': '', 'requirements': ''},
                [('product', 'product.png', data.getvalue()), ('reference', 'style.png', data.getvalue())],
                'Anonymous', mode=mode, clock=lambda: STAMP, new_id=lambda: SimpleNamespace(hex='c' * 32),
                contains_private=lambda value: False, sizes=('1024x1536',), default_requirements='default design')
            self.assertEqual(events, [('texts.json', True), ('000001.json', True), ('state.json', False), ('current.json', False)])
            self.assertEqual(files.load(state['id']), state)
            self.assertEqual(files.read_input(state['id'], state['images'][0]['file']), data.getvalue())
            self.assertEqual(state['inputs']['requirements'], 'default design' if mode == 'quick_redesign' else '')

    def test_fresh_process_executes_task_application_without_web_or_sdk(self):
        script = """
import importlib.abc,runpy,sys,unittest
class Block(importlib.abc.MetaPathFinder):
 def find_spec(self,name,*args):
  if name.split('.')[0] in {'flask','openai','prepare_plan','generate_plan_image','image_review','generate_image','quick_redesign','evidence','api'}:
   raise AssertionError('Forbidden Task dependency: '+name)
sys.meta_path.insert(0,Block())
tests=runpy.run_path(sys.argv[1])['TaskApplicationTests']
result=unittest.TextTestRunner().run(unittest.TestSuite([
 tests('test_application_runs_planning_then_state_then_applied_with_the_original_lock'),
 tests('test_creation_uses_file_boundary_for_both_modes_and_keeps_snapshot_order')]))
sys.exit(not result.wasSuccessful())
"""
        result = subprocess.run([sys.executable, '-B', '-c', script, str(Path(__file__).resolve())],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)



def task_fingerprint():
    import hashlib, json, itertools
    from pathlib import Path
    from types import SimpleNamespace
    from unittest.mock import patch
    import test_prepare_plan as fixtures
    web = fixtures.web
    fx = fixtures.PreparePlanTests()
    fx.setUp()
    try:
        identities = itertools.count(1)
        ticks = itertools.count(1)
        writes, outcomes = [], []
        original = web.write_json
        def write(path, value, exclusive=False):
            writes.append([str(path.relative_to(fx.runtime)), exclusive])
            return original(path, value, exclusive=exclusive)
        with patch.object(web, 'now', return_value='2026-01-01T00:00:00+00:00'), \
             patch.object(web, 'uuid4', side_effect=lambda: SimpleNamespace(hex=f'{next(identities):032x}')), \
             patch.object(web, 'version', return_value='offline-sdk'), \
             patch.object(web.time, 'perf_counter', side_effect=lambda: next(ticks) * .25), \
             patch.object(web, 'write_json', side_effect=write):
            state = fx.load_case()
            for kind, target, feedback in [
                ('understand', None, ''), ('reference', 'reference_001', 'correct reference'),
                ('plan', 'reference_001', 'correct plan'), ('confirm', 'reference_001', ''),
                ('confirm', 'reference_002', ''), ('product', None, 'correct product'),
                ('replan', None, ''), ('confirm', 'reference_001', '')]:
                with fx.with_ai():
                    response = fx.action(state, kind, target, feedback)
                assert response.status_code == 200, response.get_data(as_text=True)
                state = response.json['state']
                outcomes.append([kind, response.status_code, state])
            for body in [
                {'action':'confirm','target':'reference_999','revision':state['revision']},
                {'action':'plan','target':'reference_001','feedback':'','revision':state['revision']},
                {'action':'replan','revision':0},
                {'action':'unknown','revision':state['revision']}]:
                response = fx.client.post('/api/sessions/'+state['id']+'/action', headers=fixtures.HEADERS, json=body)
                outcomes.append(['invalid', response.status_code, response.json])
            # Copy inputs through the existing HTTP contract; old Task is retained.
            import io
            response = fx.client.post('/api/sessions', headers=fixtures.HEADERS, data={
                'title':'Copied task','from_session':state['id'],
                'keep_images':json.dumps([image['id'] for image in state['images']]),
                'listing':'anonymous copied listing','description':'anonymous copied description',
                'requirements':'anonymous copied requirement','mode':'product_pack'})
            assert response.status_code == 200, response.get_data(as_text=True)
            outcomes.append(['copy', response.status_code, response.json])
            tasks = fx.client.get('/api/tasks').json
            workspace = fx.client.get('/api/sessions/'+state['id']+'/workspace').json
            # E1-04 intentionally blocks NEW execution of unclassified historical
            # Listing. Assert that exact delta, then retain the pre-migration
            # golden for every other HTTP field, saved byte and write ordering.
            for card in workspace['generation']['cards']:
                assert card['generation_allowed'] is False and card['batch_eligible'] is False
                assert '历史 Listing 未保存图位分类' in card.pop('generation_block_reason')
                assert card.pop('review_allowed') == card['plan_status']['confirmed']
                card['generation_allowed'] = card['plan_status']['confirmed']
                card['batch_eligible'] = card['generation_allowed']
            workspace['generation_allowed'] = any(card['generation_allowed'] for card in workspace['generation']['cards'])
            task_rows = tasks['tasks'] if isinstance(tasks, dict) else tasks
            row = next(row for row in task_rows if row['id'] == state['id'])
            assert row['status'] == '计划待确认'
            row['status'] = '部分或全部计划已确认，待生图'
            outcomes.append(['tasks', tasks])
            outcomes.append(['workspace', workspace])
        files = {}
        source_hash = hashlib.sha256(Path(web.__file__).read_bytes()).hexdigest()
        for path in sorted(fx.runtime.rglob('*')):
            if not path.is_file(): continue
            data = path.read_bytes()
            if path.name == 'run.json':
                record = json.loads(data)
                if 'source_sha256' in record:
                    assert record['source_sha256'] == source_hash
                    record['source_sha256'] = '<ENTRY_SOURCE>'
                    data = (json.dumps(record, ensure_ascii=False, indent=2)+'\n').encode()
            files[str(path.relative_to(fx.runtime))] = hashlib.sha256(data).hexdigest()
        payload = {'files':files,'writes':writes,'outcomes':outcomes}
        digest = hashlib.sha256(json.dumps(payload,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
        return {'sha256':digest,'files':len(files),'writes':len(writes),'steps':len(outcomes)}
    finally:
        fx.doCleanups()



class TaskCompatibilityTests(unittest.TestCase):
    def test_pre_migration_task_http_state_files_and_write_order_are_equivalent(self):
        # Captured from 70c5a8b BEFORE Task/API production migration. Only the
        # entry-source hash is normalized, after checking it against the real file.
        self.assertEqual(task_fingerprint(), {"sha256":"bec711d45debc0fef48ce2babe9b32a4251d35fb33e830bbcdeb396f5d5fb725","files":60,"writes":64,"steps":15})


if __name__ == '__main__':
    unittest.main()
