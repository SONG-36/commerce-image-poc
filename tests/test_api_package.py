"""B5 HTTP identity and Task-image orchestration regressions; no real model/server."""

import ast
import copy
import hashlib
import io
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from image_workflow import Problem
from image_workflow.tasks.images import TaskImageApplication
from test_task_application import MemoryTask, ImagePeer, TARGETS


# Captured from the actual 70c5a8b Flask map before Task/API migration.
EXPECTED_ROUTES = [["/",["GET","HEAD","OPTIONS"],"home",True],["/api/case-001",["OPTIONS","POST"],"load_case",True],["/api/current",["GET","HEAD","OPTIONS"],"current",True],["/api/sessions",["OPTIONS","POST"],"save_inputs",True],["/api/sessions/<session_id>",["GET","HEAD","OPTIONS"],"saved_session",True],["/api/sessions/<session_id>/action",["OPTIONS","POST"],"action",True],["/api/sessions/<session_id>/export-experiment",["OPTIONS","POST"],"export_case",True],["/api/sessions/<session_id>/export-passed",["OPTIONS","POST"],"passed_images",True],["/api/sessions/<session_id>/generate/<target>",["OPTIONS","POST"],"generate_one",True],["/api/sessions/<session_id>/generated-images/<int:revision>/<target>/<run_id>",["GET","HEAD","OPTIONS"],"generated_image",True],["/api/sessions/<session_id>/generation",["GET","HEAD","OPTIONS"],"generation_state",True],["/api/sessions/<session_id>/images/<image_id>",["GET","HEAD","OPTIONS"],"image_file",True],["/api/sessions/<session_id>/operations/<target>/<operation_id>",["GET","HEAD","OPTIONS"],"operation_status",True],["/api/sessions/<session_id>/review/<target>",["OPTIONS","POST"],"review_one",True],["/api/sessions/<session_id>/revise/<target>",["OPTIONS","POST"],"revise_one",True],["/api/sessions/<session_id>/workspace",["GET","HEAD","OPTIONS"],"workspace_state",True],["/api/tasks",["GET","HEAD","OPTIONS"],"task_list",True],["/generate/<session_id>",["GET","HEAD","OPTIONS"],"generate_page",True],["/prepare/<session_id>",["GET","HEAD","OPTIONS"],"prepare_page",True],["/prepare/new",["GET","HEAD","OPTIONS"],"new_task_page",True],["/static/<path:filename>",["GET","HEAD","OPTIONS"],"static",True],["/workspace/<session_id>",["GET","HEAD","OPTIONS"],"prepare_page",True],["/workspace/new",["GET","HEAD","OPTIONS"],"new_task_page",True]]


class ApiContractTests(unittest.TestCase):
    def setUp(self):
        import prepare_plan as web
        self.web = web
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.app = web.create_app(Path(self.temp.name) / 'state', Path(self.temp.name) / 'case')
        self.client = self.app.test_client()

    def test_all_original_urls_methods_endpoints_and_template_static_roots_are_preserved(self):
        actual = sorted([[r.rule, sorted(r.methods), r.endpoint, r.strict_slashes] for r in self.app.url_map.iter_rules()])
        self.assertEqual(actual, EXPECTED_ROUTES)
        root = Path(self.web.__file__).parent
        self.assertEqual(self.app.import_name, 'prepare_plan')
        self.assertEqual(self.app.root_path, str(root))
        self.assertEqual(self.app.template_folder, 'templates')
        self.assertEqual(self.app.static_folder, str(root / 'static'))
        self.assertEqual(self.app.config['MAX_CONTENT_LENGTH'], 80 * 1024 * 1024)
        self.assertEqual(self.app.config['MAX_FORM_MEMORY_SIZE'], 2 * 1024 * 1024)
        for endpoint, handler in self.app.view_functions.items():
            if endpoint != 'static':
                self.assertEqual(handler.__module__, 'api.routes', endpoint)

    def test_original_entry_signature_cli_and_compatibility_names_remain(self):
        import inspect
        self.assertEqual(str(inspect.signature(self.web.create_app)), '(runtime_dir=None, case_dir=None)')
        for name in ('Store', 'call_ai', 'build_planning_request', 'OpenAI', 'write_json', 'read_json',
                     'now', 'uuid4', 'MODELS', 'task_state', 'plan_status', 'materialize_confirmations'):
            self.assertTrue(hasattr(self.web, name), name)
        tree = ast.parse(Path(self.web.__file__).read_text())
        main = next(n for n in tree.body if isinstance(n, ast.If) and isinstance(n.test, ast.Compare))
        self.assertEqual(hashlib.sha256(ast.dump(main, include_attributes=False).encode()).hexdigest(), '51888b6fd2dc0d9607f89d2cf3996afbac6062292e2d4434711a7434a1820dc1')
        factory = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'create_app')
        self.assertFalse(any(isinstance(n, ast.FunctionDef) and n is not factory for n in ast.walk(factory)))
        self.assertFalse(any(isinstance(n, ast.Name) and n.id == 'request' for n in ast.walk(tree)))

    def test_security_parsing_errors_and_busy_lock_keep_original_error_precedence(self):
        self.assertEqual(self.client.post('/api/sessions').status_code, 403)
        headers = {'X-Local-Action': 'prepare-plan'}
        wrong = {**headers, 'Origin': 'https://foreign.invalid'}
        self.assertEqual(self.client.post('/api/sessions', headers=wrong).status_code, 403)
        # The old application rejects a busy operation BEFORE parsing malformed JSON.
        store = self.app.extensions['plan_store']
        with store.lock:
            response = self.client.post('/api/sessions/' + 'a' * 32 + '/action',
                headers=headers, data='{broken', content_type='application/json')
        self.assertEqual(response.status_code, 409)
        self.assertIn('有操作正在处理', response.json['error'])
        self.app.config['MAX_CONTENT_LENGTH'] = 16
        response = self.client.post('/api/sessions', headers=headers, data={'title': 'x' * 100})
        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.json['error'], '上传体积过大，请减少图片或文件大小。')
        self.assertFalse(store.lock.locked())

    def test_free_pages_and_status_reads_do_not_construct_model_clients_or_task_data(self):
        with patch.object(self.web, 'OpenAI', side_effect=AssertionError('No model client')):
            for url in ('/', '/workspace/new', '/prepare/new', '/api/tasks', '/api/current',
                        '/static/generate.js', '/static/batch_generate.js'):
                with self.client.get(url) as response:
                    self.assertEqual(response.status_code, 200, url)
        self.assertFalse((Path(self.temp.name) / 'state').exists())

    def test_api_can_import_and_register_without_legacy_web_sdk_or_workflow_implementations(self):
        script = """
import importlib.abc,sys
from pathlib import Path
from types import SimpleNamespace
class Block(importlib.abc.MetaPathFinder):
 def find_spec(self,name,*args):
  if name.split('.')[0] in {'prepare_plan','openai','generate_image','generate_plan_image','image_review','quick_redesign','evidence'} or name.startswith(('image_workflow.tasks','image_workflow.planning','image_workflow.generation','image_workflow.review')):
   raise AssertionError('Forbidden HTTP dependency: '+name)
sys.meta_path.insert(0,Block())
sys.path.insert(0,str(Path(sys.argv[1]).resolve().parents[1]/'src'))
from flask import Flask
from api import register_routes
app=Flask('independent',root_path=str(Path(sys.argv[1]).resolve().parents[1]/'src'))
queries=SimpleNamespace(activity=lambda s:None,public=lambda s:s,confirmed_state=lambda *a:{},
 generation_view=lambda s:{},task_list=lambda:[],workspace=lambda s:{})
register_routes(app,store=SimpleNamespace(load=lambda s:{}),generation=SimpleNamespace(),
 tasks=SimpleNamespace(),queries=queries,images=SimpleNamespace(),case=None,
 safe_text=lambda s:s,auxiliary_uploads=SimpleNamespace())
assert len(list(app.url_map.iter_rules()))==23
assert app.test_client().get('/api/tasks').json=={'tasks':[]}
assert app.test_client().get('/').status_code==200
assert app.test_client().post('/api/sessions').status_code==403
"""
        result = subprocess.run([sys.executable, '-B', '-c', script, str(Path(__file__).resolve())],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)


class TaskImageUseCaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = MemoryTask(self.temp.name)
        self.generation = ImagePeer()
        self.generation.generate = Mock(return_value={'status': 'SUCCEEDED', 'run_id': 'new'})
        self.scope = copy.deepcopy(self.store.state)
        self.scope['revision'] = 1
        self.queries = SimpleNamespace(
            confirmed_state=lambda *args: self.scope,
            card_view=lambda *args: {'request_uncertain': False, 'batch_eligible': True})
        self.review = SimpleNamespace(review=Mock(return_value={'action': 'pass'}),
                                      export_passed=Mock(return_value=(io.BytesIO(b'png-zip'), 'passed.zip')))
        self.exporter = Mock(return_value=(io.BytesIO(b'evidence'), 'experiment.zip'))
        self.app = TaskImageApplication(self.store, self.generation, self.queries, review=self.review,
                                        exporter=self.exporter, safe_text=lambda value: value)
        self.body = {'confirmed_revision': 1, 'card_revision': 2, 'operation_id': 'c' * 32}

    def test_generate_uses_confirmed_snapshot_and_existing_generation_peer(self):
        result = self.app.generate_one(self.scope['id'], TARGETS[0], lambda: self.body)
        self.assertEqual(result['run_id'], 'new')
        self.generation.generate.assert_called_once_with(self.scope, TARGETS[0], expected_revision=2, operation_id='c' * 32)

    def test_uncertain_request_blocks_command_parsing_and_edit_without_execution(self):
        self.queries.card_view = lambda *args: {'request_uncertain': True}
        def unreadable():
            raise AssertionError('Uncertain operation must not parse another command')
        with self.assertRaises(Problem) as caught:
            self.app.generate_one(self.scope['id'], TARGETS[0], unreadable)
        self.assertEqual(caught.exception.status, 409)
        with self.assertRaises(Problem):
            self.app.edit_state(self.scope['id'], TARGETS[0])
        self.generation.generate.assert_not_called()

    def test_edit_validates_before_upload_then_passes_exact_parent_and_auxiliary(self):
        auxiliary = {'data': b'anonymous bytes', 'purpose': 'product_appearance'}
        read_auxiliary = Mock(return_value=auxiliary)
        with self.assertRaises(Problem):
            self.app.revise(self.scope, TARGETS[0], self.body, read_auxiliary)
        read_auxiliary.assert_not_called()
        body = {**self.body, 'parent_run_id': 'selected-run', 'feedback': 'only this image'}
        self.app.revise(self.scope, TARGETS[0], body, read_auxiliary)
        read_auxiliary.assert_called_once_with()
        self.generation.generate.assert_called_once_with(self.scope, TARGETS[0], 'selected-run',
                                                         'only this image', 2, 'c' * 32, auxiliary=auxiliary)

    def test_review_binds_exact_scope_run_and_card_version_and_preserves_error_mapping(self):
        body = {**self.body, 'action': 'pass', 'run_id': 'selected-run'}
        self.app.review_one(self.scope['id'], TARGETS[0], lambda: body)
        self.review.review.assert_called_once_with(self.generation, self.scope, TARGETS[0], 'pass', 'selected-run', 2)
        self.review.review.side_effect = OSError('offline review failure')
        with self.assertRaises(Problem) as caught:
            self.app.review_one(self.scope['id'], TARGETS[0], lambda: body)
        self.assertEqual(caught.exception.status, 409)
        self.assertEqual(str(caught.exception), 'offline review failure')

    def test_export_reuses_exact_existing_lock_scopes_and_releases_on_failure(self):
        def export(store, identity):
            self.assertTrue(store.lock.locked())
            self.assertTrue(self.generation.guard.locked())
            return io.BytesIO(b'archive'), 'experiment.zip'
        self.app.exporter = export
        self.app.export_case(self.scope['id'])
        self.assertFalse(self.store.lock.locked())
        self.assertFalse(self.generation.guard.locked())
        def accepted(generation, state):
            self.assertFalse(self.store.lock.locked())
            self.assertTrue(generation.guard.locked())
            return io.BytesIO(b'accepted'), 'passed.zip'
        self.review.export_passed.side_effect = accepted
        self.app.passed_images(self.scope['id'])
        self.generation.active.add((self.scope['id'], 1, TARGETS[0]))
        with self.assertRaises(Problem):
            self.app.export_case(self.scope['id'])
        with self.assertRaises(Problem):
            self.app.passed_images(self.scope['id'])
        self.assertFalse(self.store.lock.locked())
        self.assertFalse(self.generation.guard.locked())

    def test_quick_batch_and_version_errors_stop_before_generation(self):
        self.scope['mode'] = 'quick_redesign'
        with self.assertRaises(Problem):
            self.app.generate_one(self.scope['id'], TARGETS[0], lambda: {'confirmed_revision': 1})
        with self.assertRaises(Problem):
            self.app.generate_one(self.scope['id'], TARGETS[0], lambda: {**self.body, 'confirmed_revision': 99})
        self.queries.card_view = lambda *args: {'request_uncertain': False, 'batch_eligible': False}
        with self.assertRaises(Problem):
            self.app.generate_one(self.scope['id'], TARGETS[0], lambda: {**self.body, 'batch_only': True})
        self.generation.generate.assert_not_called()

    def test_operation_scope_precedes_revision_parse_and_query_never_executes(self):
        def unreadable():
            raise AssertionError('Foreign image must not parse a revision')
        with self.assertRaises(Problem) as caught:
            self.app.operation_status(self.scope['id'], 'reference_999', 'operation', unreadable)
        self.assertEqual(caught.exception.status, 404)
        self.generation.operation = Mock(return_value={'status': 'NOT_FOUND', 'uncertain': True})
        result = self.app.operation_status(self.scope['id'], TARGETS[0], 'operation', lambda: '1')
        self.assertTrue(result['uncertain'])
        self.generation.operation.assert_called_once()
        self.generation.generate.assert_not_called()


if __name__ == '__main__':
    unittest.main()
