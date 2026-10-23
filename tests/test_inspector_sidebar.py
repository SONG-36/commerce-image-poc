"""Local opt-in integration, anonymous files and SDK MockTransport only."""

import base64
from concurrent.futures import ThreadPoolExecutor
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from uuid import uuid4

import httpx
import test_generate_plan_image as generation_fixture
import test_workflow_inspector as evidence_fixture
from api.inspector import create_inspector_app
import app
from file_ops import sha256


class InspectorSidebarTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / 'isolated'
        self.folder = evidence_fixture.make_evidence(self.root)
        self.app = app.create_local_debug_app(self.root, [evidence_fixture.TASK])
        self.client = self.app.test_client()
        self.url = '/api/inspector/tasks/' + evidence_fixture.TASK
        self.enterContext(patch('socket.socket.connect', side_effect=AssertionError('No network')))

    def fingerprint(self):
        return {p.relative_to(self.root).as_posix(): (sha256(p.read_bytes()), p.stat().st_mtime_ns)
                for p in self.root.rglob('*') if p.is_file()}

    def test_default_factory_is_unchanged_and_sidebar_is_opt_in_and_task_scoped(self):
        normal = app.create_app(self.root).test_client()
        page = '/workspace/' + evidence_fixture.TASK
        self.assertNotIn(b'id="toggle-inspector"', normal.get(page).data)
        self.assertEqual(normal.get(self.url).status_code, 404)
        self.assertEqual(len(list(normal.application.url_map.iter_rules())), 23)
        self.assertIn(b'id="toggle-inspector"', self.client.get(page).data)
        foreign = self.root / 'sessions' / evidence_fixture.OTHER
        foreign.mkdir()
        state = json.loads((self.folder / 'state.json').read_text())
        state['id'] = evidence_fixture.OTHER
        (foreign / 'state.json').write_text(json.dumps(state))
        self.assertNotIn(b'id="toggle-inspector"', self.client.get('/workspace/' + evidence_fixture.OTHER).data)
        self.assertEqual(self.client.get('/api/inspector/tasks/' + evidence_fixture.OTHER).status_code, 404)

    def test_requires_explicit_isolation_and_nonempty_valid_task_allowlist(self):
        for root in (None, '', app.ROOT / '.runtime/prepare-plan', app.ROOT / '.runtime/prepare-plan/sessions'):
            with self.subTest(root=root), self.assertRaises(ValueError):
                app.create_local_debug_app(root, [evidence_fixture.TASK])
        for tasks in ([], ['*'], ['../' + evidence_fixture.TASK]):
            with self.subTest(tasks=tasks), self.assertRaises(ValueError):
                app.create_local_debug_app(self.root, tasks)
        alias = self.root.parent / 'alias'
        # Exercise the production-root alias rule wholly inside temporary storage.
        with patch.object(app, 'ROOT', self.root.parent / 'anonymous-project'):
            alias.symlink_to(app.ROOT / '.runtime/prepare-plan', target_is_directory=True)
            with self.assertRaises(ValueError):
                app.create_local_debug_app(alias, [evidence_fixture.TASK])

    def test_entire_debug_app_rejects_lan_forwarding_cross_site_and_host_rebinding(self):
        for path in ('/', '/api/current', self.url, '/static/debug_sidebar.js', '/inspector?embedded=1'):
            for headers, env in (({}, {'REMOTE_ADDR': '192.168.112.3'}), ({'Host': 'evil.invalid'}, {}),
                                 ({'X-Forwarded-For': '127.0.0.1'}, {}), ({'Origin': 'https://evil.invalid'}, {})):
                with self.subTest(path=path, headers=headers, env=env):
                    self.assertEqual(self.client.get(path, headers=headers, environ_overrides=env).status_code, 404)

    def test_integrated_api_and_assets_equal_standalone_and_leave_evidence_unchanged(self):
        standalone = create_inspector_app(self.root, [evidence_fixture.TASK]).test_client()
        before = self.fingerprint()
        for image, run in [('reference_001', evidence_fixture.RUN), ('reference_002', evidence_fixture.FAILED)]:
            query = f'?image_id={image}&revision=3&run_id={run}'
            integrated = self.client.get(self.url + query)
            self.assertEqual(integrated.status_code, 200)
            self.assertEqual(integrated.json, standalone.get(self.url + query).json)
            for asset in integrated.json['assets']:
                if asset['status'] == 'OBSERVED':
                    path = self.url + '/assets/' + asset['key'] + query
                    result = self.client.get(path)
                    self.assertEqual(result.status_code, 200)
                    self.assertEqual(result.data, standalone.get(path).data)
            self.assertNotIn(evidence_fixture.CANARY, integrated.get_data(as_text=True))
            self.assertNotIn('HIDDEN_CANARY', integrated.get_data(as_text=True))
        for method in ('POST', 'PUT', 'PATCH', 'DELETE'):
            self.assertEqual(self.client.open(self.url, method=method, headers=generation_fixture.HEADERS).status_code, 405)
        self.assertEqual(self.fingerprint(), before)

    def test_embedding_is_same_origin_only_and_standalone_remains_available(self):
        embedded = self.client.get('/inspector?embedded=1')
        self.assertIn(b'data-embedded="true"', embedded.data)
        self.assertIn("frame-ancestors 'self'", embedded.headers['Content-Security-Policy'])
        independent = self.client.get('/inspector')
        self.assertNotIn(b'data-embedded="true"', independent.data)
        self.assertIn("frame-ancestors 'none'", independent.headers['Content-Security-Policy'])
        old = create_inspector_app(self.root, [evidence_fixture.TASK]).test_client().get('/inspector?embedded=1')
        self.assertNotIn(b'data-embedded="true"', old.data)
        self.assertIn("frame-ancestors 'none'", old.headers['Content-Security-Policy'])

    def test_integrated_path_and_cross_image_run_guards_remain_enforced(self):
        before = self.fingerprint()
        for suffix in ('/assets/..%2F..%2F.env', '?image_id=reference_002&revision=3&run_id=' + evidence_fixture.RUN,
                       '?image_id=reference_001&revision=../3', '/assets/unknown'):
            self.assertEqual(self.client.get(self.url + suffix).status_code, 404)
        input_file = self.folder / 'inputs/product_001.png'
        input_file.unlink()
        input_file.symlink_to(self.folder / 'inputs/reference_001.png')
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(len(before), len(self.fingerprint()))

    def test_frontend_sidebar_and_embedded_request_coordination_offline(self):
        result = subprocess.run(['node', '--test', str(Path(__file__).with_name('inspector_sidebar.test.cjs'))],
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_local_debug_launcher_requires_explicit_runtime_and_task_without_starting(self):
        source = Path(__file__).resolve().parents[1] / 'src'
        command = [sys.executable, '-B', '-m', 'cli.debug_workspace']
        help_result = subprocess.run(command + ['--help'], cwd=source, capture_output=True, text=True, timeout=10)
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        self.assertIn('--runtime-dir', help_result.stdout)
        self.assertIn('--task-id', help_result.stdout)
        missing = subprocess.run(command, cwd=source, capture_output=True, text=True, timeout=10)
        self.assertEqual(missing.returncode, 2)


class InspectorBusinessCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.fx = generation_fixture.GenerationPageTests()
        self.fx.setUp()
        self.addCleanup(self.fx.doCleanups)
        self.app = app.create_local_debug_app(self.fx.runtime, [self.fx.state['id']])
        self.client = self.app.test_client()
        self.fx.app, self.fx.client = self.app, self.client
        self.state = self.fx.state
        self.url = '/api/inspector/tasks/' + self.state['id']

    def card(self):
        return self.client.get(f"/api/sessions/{self.state['id']}/workspace").json['generation']['cards'][0]

    def test_generate_edit_select_pass_remain_business_commands_inspector_stays_read_only(self):
        with self.fx.with_sdk():
            generated = self.fx.post('reference_001')
        self.assertEqual(generated.status_code, 200)
        first = generated.json['run_id']
        review_url = f"/api/sessions/{self.state['id']}/review/reference_001"
        def review(action, run):
            return self.client.post(review_url, headers=generation_fixture.HEADERS, json={
                'action': action, 'run_id': run, 'confirmed_revision': self.state['revision'], 'card_revision': self.card()['card_revision']})
        self.assertEqual(review('pass', first).status_code, 200)
        with self.fx.with_sdk():
            edited = self.client.post(f"/api/sessions/{self.state['id']}/revise/reference_001", headers=generation_fixture.HEADERS,
                data={'confirmed_revision': str(self.state['revision']), 'card_revision': str(self.card()['card_revision']),
                      'operation_id': uuid4().hex, 'parent_run_id': first, 'feedback': '匿名修改，保持外观',
                      'auxiliary_purpose': 'product_appearance', 'auxiliary': (io.BytesIO(generation_fixture.png()), 'same-sku.png')})
        self.assertEqual(edited.status_code, 200, edited.json)
        second = edited.json['run_id']
        self.assertNotEqual(first, second)
        self.assertEqual(self.card()['passed_run'], first)
        self.assertEqual(review('select', first).status_code, 200)
        before = {str(p): p.read_bytes() for p in self.fx.runtime.rglob('*') if p.is_file()}
        count = len(self.fx.requests)
        for run in (first, second):
            r = self.client.get(self.url + f'?image_id=reference_001&revision={self.state["revision"]}&run_id={run}')
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.json['selection']['run_id'], run)
            if run == second:
                self.assertEqual(r.json['nodes'][4]['status'], 'MISSING')
                self.assertTrue(any(a['role'] == 'auxiliary_reference' for a in r.json['assets']))
        self.assertEqual(len(self.fx.requests), count)
        self.assertEqual({str(p): p.read_bytes() for p in self.fx.runtime.rglob('*') if p.is_file()}, before)
        self.assertEqual(self.card()['selected_run'], first)
        self.assertEqual(self.card()['passed_run'], first)

    def test_quick_run_has_no_planning_and_uses_same_inspector(self):
        state = self.app.extensions['plan_store'].create({'listing': '', 'description': '', 'requirements': '匿名重设计'},
                [('product', 'original.png', generation_fixture.png())], '匿名 Quick', mode='quick_redesign')
        self.app = app.create_local_debug_app(self.fx.runtime, [self.state['id'], state['id']])
        self.client = self.app.test_client()
        with self.fx.with_sdk():
            result = self.client.post(f"/api/sessions/{state['id']}/generate/product_001", headers=generation_fixture.HEADERS,
                                     json={'confirmed_revision': state['revision'], 'card_revision': 0, 'operation_id': uuid4().hex})
        self.assertEqual(result.status_code, 200, result.json)
        view = self.client.get('/api/inspector/tasks/' + state['id'] + '?image_id=product_001').json
        self.assertEqual(view['selection']['run_id'], result.json['run_id'])
        self.assertEqual(view['nodes'][1]['status'], 'NOT_APPLICABLE')
        self.assertEqual(view['nodes'][1]['documents'], [])

    def test_inspector_does_not_wait_on_running_model_or_take_business_locks(self):
        entered, release = threading.Event(), threading.Event()
        def transport(request):
            entered.set()
            if not release.wait(5):
                raise AssertionError('Test did not release Mock model')
            return httpx.Response(200, json={'data': [{'b64_json': base64.b64encode(generation_fixture.png((1024, 1536))).decode()}]})
        with self.fx.with_sdk(transport), ThreadPoolExecutor(max_workers=2) as pool:
            generated = pool.submit(lambda: self.app.test_client().post(f"/api/sessions/{self.state['id']}/generate/reference_001",
                headers=generation_fixture.HEADERS, json={'confirmed_revision': self.state['revision']}))
            try:
                self.assertTrue(entered.wait(3))
                response = pool.submit(lambda: self.app.test_client().get(self.url + '?image_id=reference_001')).result(timeout=2)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json['nodes'][3]['execution_status'], 'RUNNING')
                service = self.app.extensions['generation_service']
                self.assertEqual(len(service.active), 1)
            finally:
                release.set()
            self.assertEqual(generated.result(timeout=3).status_code, 200)


if __name__ == '__main__':
    unittest.main()
