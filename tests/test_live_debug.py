"""Local debug configuration/authorization only; anonymous data and no model calls."""

import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

import httpx

import app
import test_generate_plan_image as fixtures
import test_workflow_inspector as evidence


class LiveDebugTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / 'isolated'
        self.folder = evidence.make_evidence(self.root)
        self.enterContext(patch('socket.socket.connect', side_effect=AssertionError('Network forbidden')))

    def client(self, mode='LIVE DEBUG', paid=False):
        return app.create_local_debug_app(self.root, [evidence.TASK], execution_mode=mode,
                                           allow_paid_actions=paid).test_client()

    def files(self):
        return {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}

    def test_environment_is_server_configuration_and_never_inferred_from_key(self):
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'synthetic-offline-canary'}):
            for mode in ('MOCK', 'LIVE DEBUG', 'UNVERIFIED'):
                client = self.client(mode)
                result = client.get('/api/inspector/access?task_id=' + evidence.TASK)
                self.assertEqual(result.status_code, 200)
                self.assertEqual(result.json['mode'], mode)
                self.assertTrue(result.json['key_configured'])
                self.assertFalse(result.json['paid_actions_enabled'])
                self.assertTrue(result.json['authorized'])
                self.assertEqual(result.json['runtime_dir'], str(self.root))
                self.assertEqual(result.json['pid'], os.getpid())
                page = client.get('/workspace/' + evidence.TASK).get_data(as_text=True)
                self.assertIn(mode, page)
                self.assertNotIn('synthetic-offline-canary', page + result.get_data(as_text=True))
        with self.assertRaises(ValueError):
            self.client('anything-from-browser')

    def test_access_check_does_not_grant_or_read_foreign_tasks_or_mutate_files(self):
        client = self.client('MOCK')
        before = self.files()
        for identity in (evidence.OTHER, '../state.json', '*'):
            result = client.get('/api/inspector/access', query_string={'task_id': identity})
            self.assertEqual(result.status_code, 200)
            self.assertFalse(result.json['authorized'])
        result = client.get('/api/inspector/tasks/' + evidence.OTHER)
        self.assertEqual(result.status_code, 404)
        self.assertEqual(result.json['code'], 'TASK_NOT_AUTHORIZED')
        self.assertEqual(client.post('/api/inspector/access', headers=fixtures.HEADERS,
                                     json={'task_id': evidence.OTHER}).status_code, 405)
        self.assertEqual(self.files(), before)

    def test_new_task_stays_unauthorized_until_explicit_server_restart_configuration(self):
        client = self.client('MOCK')
        result = client.post('/api/sessions', headers=fixtures.HEADERS, data={
            'title': '匿名新增调试任务', 'mode': 'quick_redesign', 'requirements': '保留外观',
            'product': (io.BytesIO(fixtures.png()), 'anonymous.png')})
        self.assertEqual(result.status_code, 200, result.json)
        identity = result.json['state']['id']
        self.assertFalse(client.get('/api/inspector/access?task_id=' + identity).json['authorized'])
        self.assertEqual(client.get('/api/inspector/tasks/' + identity).status_code, 404)
        page = client.get('/workspace/' + identity).get_data(as_text=True)
        self.assertIn('当前 Task 未获调试授权', page)
        configured = app.create_local_debug_app(self.root, [identity], execution_mode='MOCK').test_client()
        self.assertTrue(configured.get('/api/inspector/access?task_id=' + identity).json['authorized'])
        view = configured.get('/api/inspector/tasks/' + identity)
        self.assertEqual(view.status_code, 200)
        self.assertEqual(view.json['selection']['task_id'], identity)
        self.assertEqual(view.json['nodes'][1]['status'], 'NOT_APPLICABLE')
        self.assertFalse(client.get('/api/inspector/access?task_id=' + identity).json['authorized'])

    def test_live_paid_lock_rejects_before_run_writes_or_client_creation(self):
        client = self.client()
        before = self.files()
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'synthetic-offline-canary'}), \
                patch('infrastructure.openai_images.OpenAI', side_effect=AssertionError('No client')):
            for operation in ('generate', 'revise'):
                result = client.post(f'/api/sessions/{evidence.TASK}/{operation}/reference_001',
                                     headers=fixtures.HEADERS, json={})
                self.assertEqual(result.status_code, 403)
                self.assertEqual(result.json['code'], 'LIVE_CALLS_LOCKED')
            result = client.post('/api/sessions/' + evidence.TASK + '/action', headers=fixtures.HEADERS,
                                 json={'action': 'understand'})
            self.assertEqual(result.json['code'], 'LIVE_CALLS_LOCKED')
        self.assertEqual(self.files(), before)

    def test_live_key_absence_and_foreign_task_remain_locked_even_with_paid_flag(self):
        client = self.client(paid=True)
        with patch.dict(os.environ, {'OPENAI_API_KEY': ''}):
            result = client.post('/api/sessions/' + evidence.TASK + '/generate/reference_001',
                                 headers=fixtures.HEADERS, json={})
            self.assertEqual(result.json['code'], 'LIVE_CALLS_LOCKED')
        result = client.post('/api/sessions/' + evidence.OTHER + '/generate/reference_001',
                             headers=fixtures.HEADERS, json={})
        self.assertEqual(result.status_code, 403)
        self.assertEqual(result.json['code'], 'TASK_NOT_AUTHORIZED')

    def test_paid_gate_does_not_block_free_review_or_existing_evidence_reads(self):
        client = self.client()
        self.assertEqual(client.get('/api/inspector/tasks/' + evidence.TASK).status_code, 200)
        created = client.post('/api/sessions', headers=fixtures.HEADERS, data={
            'title': '匿名审核任务', 'mode': 'quick_redesign',
            'product': (io.BytesIO(fixtures.png()), 'anonymous.png')})
        self.assertEqual(created.status_code, 200, created.json)
        identity = created.json['state']['id']
        # An invalid review reaches the original business validator, not the AI gate.
        result = client.post('/api/sessions/' + identity + '/review/product_001',
                             headers=fixtures.HEADERS, json={})
        self.assertEqual(result.status_code, 409)
        self.assertNotEqual(result.json.get('code'), 'LIVE_CALLS_LOCKED')
        normal = app.create_app(self.root).test_client()
        self.assertEqual(normal.get('/api/inspector/access').status_code, 404)
        self.assertNotIn(b'id="debug-environment"', normal.get('/workspace/' + evidence.TASK).data)

    def test_access_metadata_obeys_existing_loopback_forwarding_and_cross_site_guards(self):
        client = self.client()
        for headers, environment in (({'Host': 'evil.invalid'}, {}), ({'X-Forwarded-For': '127.0.0.1'}, {}),
                                     ({'Origin': 'https://evil.invalid'}, {}), ({}, {'REMOTE_ADDR': '192.168.112.3'})):
            self.assertEqual(client.get('/api/inspector/access', headers=headers,
                                        environ_overrides=environment).status_code, 404)

    def test_fresh_live_launcher_has_official_factory_and_no_fixture_imports(self):
        script = '''
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from app import create_local_debug_app
from infrastructure import openai_images
from image_workflow.tasks import generation_runtime
application = create_local_debug_app(Path(sys.argv[2])/'fresh', ['a'*32], execution_mode='LIVE DEBUG')
runtime = application.extensions['generation_service']._runtime()
assert runtime.io.client_factory is openai_images.make_client
assert runtime.io.client_factory.__module__ == 'infrastructure.openai_images'
assert runtime.timeout_seconds == 180.0
assert not any(name.startswith(('test_', 'tests.')) for name in sys.modules)
assert not (Path(sys.argv[2])/'fresh').exists()
'''
        source = Path(__file__).resolve().parents[1] / 'src'
        result = subprocess.run([sys.executable, '-B', '-c', script, str(source), str(self.root.parent)],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        # Empty Key now starts a locked page rather than rejecting the launch.
        # Keep this check isolated from the real project's .env and listener.
        from cli import debug_workspace
        with patch.dict(os.environ, {'OPENAI_API_KEY': ''}), \
                patch.object(debug_workspace, 'PROJECT_ROOT', self.root.parent), \
                patch.object(sys, 'argv', ['debug_workspace', '--runtime-dir', str(self.root),
                                          '--task-id', evidence.TASK, '--allow-paid-actions']), \
                patch.object(app, 'create_local_debug_app') as factory, patch('builtins.print'):
            debug_workspace.main()
        self.assertFalse(factory.call_args.kwargs['allow_paid_actions'])
        factory.return_value.run.assert_called_once()


class RuntimeLiveDebugTests(unittest.TestCase):
    """Real HTTP/use-case/Evidence paths with synthetic SDK responses only."""

    def setUp(self):
        self.fx = fixtures.GenerationPageTests()
        self.fx.setUp()
        self.addCleanup(self.fx.doCleanups)
        self.root = self.fx.runtime
        self.app = app.create_local_debug_app(self.root, execution_mode='LIVE DEBUG',
                                               allow_runtime_tasks=True, allow_paid_actions=True)
        self.client = self.app.test_client()
        self.enterContext(patch('socket.socket.connect', side_effect=AssertionError('No network')))

    def create(self, title):
        result = self.client.post('/api/sessions', headers=fixtures.HEADERS, data={
            'title': title, 'mode': 'quick_redesign', 'requirements': '匿名外观保持',
            'product': (io.BytesIO(fixtures.png()), 'anonymous.png')})
        self.assertEqual(result.status_code, 200, result.json)
        return result.json['state']

    def card(self, state):
        return self.client.get('/api/sessions/' + state['id'] + '/workspace').json['generation']['cards'][0]

    def generate(self, state, operation=None, card_revision=None):
        return self.client.post('/api/sessions/' + state['id'] + '/generate/product_001',
            headers=fixtures.HEADERS, json={'confirmed_revision': state['revision'],
                'card_revision': self.card(state)['card_revision'] if card_revision is None else card_revision,
                'operation_id': operation or uuid4().hex})

    def files(self):
        return {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}

    def test_two_new_tasks_generate_edit_and_inspect_without_restart_or_grants(self):
        self.assertIn(b'id="toggle-inspector"', self.client.get('/workspace/new').data)
        tasks, runs = [], []
        with self.fx.with_sdk():
            for title in ('匿名第一任务', '匿名第二任务'):
                state = self.create(title)
                tasks.append(state)
                access = self.client.get('/api/inspector/access?task_id=' + state['id']).json
                self.assertEqual(access['task_scope'], 'runtime')
                self.assertTrue(access['authorized'])
                operation = uuid4().hex
                generated = self.generate(state, operation)
                self.assertEqual(generated.status_code, 200, generated.json)
                run = generated.json['run_id']
                runs.append(run)
                # Same operation is reused even if the submitted card revision is stale.
                repeated = self.generate(state, operation, card_revision=0)
                self.assertEqual(repeated.status_code, 200, repeated.json)
                self.assertEqual(repeated.json['run_id'], run)
                view = self.client.get('/api/inspector/tasks/' + state['id'], query_string={
                    'image_id': 'product_001', 'revision': state['revision'], 'run_id': run})
                self.assertEqual(view.status_code, 200, view.json)
                self.assertEqual(view.json['selection']['task_id'], state['id'])
                self.assertEqual(view.json['selection']['run_id'], run)
                self.assertEqual(view.json['nodes'][1]['status'], 'NOT_APPLICABLE')
                self.assertTrue(any(asset['role'] == 'output' and asset['status'] == 'OBSERVED' for asset in view.json['assets']))
            self.assertEqual(len(self.fx.requests), 2)
            first_bytes = {str(p): p.read_bytes() for p in (self.root / 'sessions' / tasks[0]['id']).rglob('*') if p.is_file()}
            state = tasks[1]
            review_url = '/api/sessions/' + state['id'] + '/review/product_001'
            passed = self.client.post(review_url, headers=fixtures.HEADERS, json={
                'confirmed_revision': state['revision'], 'card_revision': self.card(state)['card_revision'],
                'action': 'pass', 'run_id': runs[1]})
            self.assertEqual(passed.status_code, 200, passed.json)
            edited = self.client.post('/api/sessions/' + state['id'] + '/revise/product_001',
                headers=fixtures.HEADERS, data={'confirmed_revision': str(state['revision']),
                    'card_revision': str(self.card(state)['card_revision']), 'operation_id': uuid4().hex,
                    'parent_run_id': runs[1], 'feedback': '匿名修改', 'auxiliary_purpose': 'product_appearance',
                    'auxiliary': (io.BytesIO(fixtures.png()), 'same-sku.png')})
            self.assertEqual(edited.status_code, 200, edited.json)
            self.assertNotEqual(edited.json['run_id'], runs[1])
            self.assertEqual(self.card(state)['passed_run'], runs[1])
            self.assertEqual(len(self.fx.requests), 3)
            self.assertEqual(first_bytes, {str(p): p.read_bytes() for p in (self.root / 'sessions' / tasks[0]['id']).rglob('*') if p.is_file()})
        count = len(self.fx.requests)
        before = self.files()
        view = self.client.get('/api/inspector/tasks/' + state['id'], query_string={
            'image_id': 'product_001', 'revision': state['revision'], 'run_id': edited.json['run_id']})
        self.assertEqual(view.status_code, 200, view.json)
        self.assertTrue(any(asset['role'] == 'auxiliary_reference' for asset in view.json['assets']))
        for asset in view.json['assets']:
            if asset['status'] == 'OBSERVED':
                result = self.client.get('/api/inspector/tasks/' + state['id'] + '/assets/' + asset['key'],
                    query_string={'image_id': 'product_001', 'revision': state['revision'], 'run_id': edited.json['run_id']})
                self.assertEqual(result.status_code, 200)
        foreign = self.client.get('/api/inspector/tasks/' + tasks[0]['id'], query_string={
            'image_id': 'product_001', 'revision': tasks[0]['revision'], 'run_id': edited.json['run_id']})
        self.assertEqual(foreign.status_code, 404)
        listed = self.client.get('/api/inspector/tasks').json['tasks']
        self.assertTrue({state['id'] for state in tasks}.issubset({row['id'] for row in listed}))
        self.assertEqual(self.files(), before)
        self.assertEqual(len(self.fx.requests), count)

    def test_runtime_scope_rejects_missing_malformed_mismatched_and_symlink_tasks(self):
        before = self.files()
        invalid = [evidence.OTHER, '../state.json', '*']
        for identity in ('c' * 32, 'd' * 32, 'e' * 32):
            folder = self.root / 'sessions' / identity
            folder.mkdir()
            if identity[0] == 'c':
                (folder / 'state.json').write_text('{broken')
            elif identity[0] == 'd':
                (folder / 'state.json').write_text(json.dumps({'id': 'wrong'}))
            else:
                (folder / 'state.json').symlink_to(self.root / 'sessions' / self.fx.state['id'] / 'state.json')
            invalid.append(identity)
        outside = self.root.parent / 'outside-task'
        outside.mkdir()
        linked = 'f' * 32
        (outside / 'state.json').write_text(json.dumps({'id': linked}))
        (self.root / 'sessions' / linked).symlink_to(outside, target_is_directory=True)
        invalid.append(linked)
        with patch('infrastructure.openai_images.OpenAI', side_effect=AssertionError('No SDK client')):
            for identity in invalid:
                result = self.client.get('/api/inspector/access', query_string={'task_id': identity})
                self.assertFalse(result.json['authorized'])
                if len(identity) == 32:
                    denied = self.client.post('/api/sessions/' + identity + '/generate/product_001', headers=fixtures.HEADERS, json={})
                    self.assertEqual(denied.status_code, 403)
                    self.assertFalse(denied.json['api_call_attempted'])
                    self.assertEqual(self.client.get('/api/inspector/tasks/' + identity).status_code, 404)
        rows = self.client.get('/api/inspector/tasks').json['tasks']
        self.assertEqual([row['id'] for row in rows], [self.fx.state['id']])
        self.assertTrue(all(self.files()[name] == value for name, value in before.items()))
        self.assertEqual(list(self.root.glob('sessions/*/generations')), [])

    def test_missing_key_and_paid_lock_still_reject_before_model_or_run(self):
        state = self.create('匿名无 Key')
        before = self.files()
        with patch.dict(os.environ, {'OPENAI_API_KEY': ''}), \
                patch('infrastructure.openai_images.OpenAI', side_effect=AssertionError('No client')):
            result = self.generate(state)
            self.assertEqual(result.status_code, 403)
            self.assertEqual(result.json['code'], 'LIVE_CALLS_LOCKED')
            self.assertFalse(result.json['api_call_attempted'])
            self.assertIn('OpenAI API Key', result.json['error'])
        self.assertEqual(self.files(), before)

    def test_runtime_scope_is_opt_in_live_only_and_production_inspector_stays_closed(self):
        for mode in ('MOCK', 'UNVERIFIED'):
            with self.assertRaises(ValueError):
                app.create_local_debug_app(self.root, execution_mode=mode, allow_runtime_tasks=True)
        normal = app.create_app(self.root).test_client()
        self.assertEqual(normal.get('/api/inspector/tasks').status_code, 404)
        self.assertEqual(len(list(normal.application.url_map.iter_rules())), 23)
        for headers, environment in (({'Host': 'evil.invalid'}, {}), ({'X-Forwarded-For': '127.0.0.1'}, {}),
                ({'Origin': 'https://evil.invalid'}, {}), ({'Sec-Fetch-Site': 'cross-site'}, {}),
                ({}, {'REMOTE_ADDR': '192.168.112.3'})):
            self.assertEqual(self.client.get('/api/inspector/tasks', headers=headers, environ_overrides=environment).status_code, 404)

    def test_product_pack_still_requires_confirmed_plan_then_uses_same_workflow(self):
        state = self.fx.state
        with self.fx.with_sdk():
            generated = self.client.post('/api/sessions/' + state['id'] + '/generate/reference_001',
                headers=fixtures.HEADERS, json={'confirmed_revision': state['revision'], 'operation_id': uuid4().hex})
        self.assertEqual(generated.status_code, 200, generated.json)
        changed = self.app.extensions['plan_store'].load(state['id'])
        changed['confirmed'] = False
        self.app.extensions['plan_store'].save(changed, {'action': 'offline_unconfirm'})
        rejected = self.client.post('/api/sessions/' + state['id'] + '/generate/reference_002',
            headers=fixtures.HEADERS, json={'confirmed_revision': changed['revision'], 'operation_id': uuid4().hex})
        self.assertEqual(rejected.status_code, 409, rejected.json)
        self.assertEqual(len(self.fx.requests), 1)

    def test_api_authentication_failure_is_real_failure_recorded_once_and_sanitized(self):
        state = self.create('匿名认证失败')
        with self.fx.with_sdk(lambda request: httpx.Response(401, json={
                'error': {'message': 'Invalid API key', 'type': 'invalid_api_key'}})):
            result = self.generate(state)
        self.assertEqual(result.status_code, 502, result.json)
        self.assertEqual(len(self.fx.requests), 1)
        run_file = next((self.root / 'sessions' / state['id']).glob('generations/**/run.json'))
        record = json.loads(run_file.read_text())
        self.assertEqual(record['status'], 'FAILED')
        self.assertEqual(record['error']['type'], 'AuthenticationError')
        self.assertFalse((run_file.parent / 'image.png').exists())
        self.assertNotIn(os.environ['OPENAI_API_KEY'], result.get_data(as_text=True))
