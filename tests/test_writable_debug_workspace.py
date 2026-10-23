"""Read-only anonymous preview versus writable Live Debug; SDK Mock only."""

import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

import app
from file_ops import sha256
from test_context_inspector import anonymous_image, make_quick_evidence, mock_client, CANARY, HEADERS


class WritableDebugWorkspaceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / 'isolated-debug-runtime'
        self.enterContext(patch('socket.socket.connect', side_effect=AssertionError('No real network')))

    def files(self):
        return {str(p.relative_to(self.root)): sha256(p.read_bytes()) for p in self.root.rglob('*') if p.is_file()}

    def data(self, title='NEW FIXTURE · 可写任务'):
        return {'mode': 'quick_redesign', 'title': title, 'requirements': '改善排版，保持原商品外观。',
                'product_facts': '匿名蓝色瓶体，不添加配件。',
                'product': (io.BytesIO(anonymous_image()), 'anonymous.png'),
                'reference': (io.BytesIO(anonymous_image('reference')), 'anonymous-style.png')}

    def test_read_only_preview_announces_mode_and_rejects_every_write_before_business(self):
        _, state, run, _ = make_quick_evidence(self.root)
        application = app.create_local_debug_app(self.root, [state['id']], execution_mode='MOCK', read_only_workspace=True)
        client = application.test_client()
        config = client.get('/api/inspector/access?task_id=' + state['id']).json
        self.assertTrue(config['read_only_workspace'])
        page = client.get('/workspace/' + state['id']).get_data(as_text=True)
        self.assertIn('匿名只读预览', page)
        self.assertIn('data-workspace-read-only="true"', page)
        self.assertIn('<fieldset class="input-fields" disabled>', page)
        self.assertIn('id="save-inputs" class="primary" disabled', page)
        self.assertNotIn('href="/workspace/new"', client.get('/').get_data(as_text=True))
        before = self.files()
        paths = ['/api/sessions', '/api/case-001', *[
            '/api/sessions/' + state['id'] + '/' + action for action in
            ('action', 'generate/product_001', 'revise/product_001', 'review/product_001', 'export-experiment', 'export-passed')]]
        with patch.object(application.extensions['plan_store'], 'create', side_effect=AssertionError('No writes')), \
                patch('infrastructure.openai_images.OpenAI', side_effect=AssertionError('No SDK')):
            for path in paths:
                for method in ('POST', 'PUT', 'PATCH', 'DELETE'):
                    with self.subTest(path=path, method=method):
                        self.assertEqual(client.open(path, method=method, headers=HEADERS, json={}).status_code, 405)
        view = client.get('/api/inspector/tasks/' + state['id']).json
        self.assertEqual(view['selection']['run_id'], run)
        self.assertEqual(len(view['graph_view']['nodes']), 17)
        self.assertEqual(len(view['graph_view']['edges']), 21)
        self.assertEqual(self.files(), before)

    def test_live_new_save_as_tasks_and_switch_need_no_allowlist_or_restart(self):
        application = app.create_local_debug_app(self.root, execution_mode='LIVE DEBUG', allow_runtime_tasks=True)
        client = application.test_client()
        first = client.post('/api/sessions', headers=HEADERS, data=self.data()).json['state']
        before = self.files()
        second = client.post('/api/sessions', headers=HEADERS, data={
            'mode': 'quick_redesign', 'title': 'NEW FIXTURE · 另存副本', 'requirements': '只改变设计要求。',
            'from_session': first['id'], 'keep_images': json.dumps([image['id'] for image in first['images']])})
        self.assertEqual(second.status_code, 200, second.json)
        second = second.json['state']
        self.assertNotEqual(first['id'], second['id'])
        for state in (first, second):
            config = client.get('/api/inspector/access?task_id=' + state['id']).json
            self.assertTrue(config['authorized'])
            self.assertEqual(config['task_scope'], 'runtime')
            self.assertFalse(config['read_only_workspace'])
            page = client.get('/workspace/' + state['id']).get_data(as_text=True)
            self.assertIn('data-workspace-read-only="false"', page)
            self.assertNotIn('id="read-only-notice"', page)
            self.assertIn('V0.7', page)
            self.assertEqual(client.get('/api/sessions/' + state['id'] + '/workspace').json['state']['id'], state['id'])
            self.assertTrue(client.get('/api/inspector/tasks/' + state['id']).json['graph_view']['awaiting_run'])
        self.assertTrue(all(self.files()[key] == value for key, value in before.items() if key.startswith('sessions/')))

    def test_live_official_workflow_mock_generate_edit_and_inspector_follow_real_run_ids(self):
        application = app.create_local_debug_app(self.root, execution_mode='LIVE DEBUG',
                                                 allow_runtime_tasks=True, allow_paid_actions=True)
        client = application.test_client()
        result = client.post('/api/sessions', headers=HEADERS, data=self.data())
        self.assertEqual(result.status_code, 200, result.json)
        state = result.json['state']
        calls = []
        url = '/api/sessions/' + state['id']
        with patch.dict(os.environ, {'OPENAI_API_KEY': CANARY}), mock_client(calls):
            generated = client.post(url + '/generate/product_001', headers=HEADERS,
                json={'confirmed_revision': 1, 'card_revision': 0, 'operation_id': uuid4().hex})
            self.assertEqual(generated.status_code, 200, generated.json)
            parent = generated.json['run_id']
            before = self.files()
            edited = client.post(url + '/revise/product_001', headers=HEADERS,
                data={'confirmed_revision': '1', 'card_revision': '2', 'operation_id': uuid4().hex,
                      'parent_run_id': parent, 'feedback': '只修正瓶盖颜色。', 'auxiliary_purpose': 'product_appearance',
                      'auxiliary': (io.BytesIO(anonymous_image()), 'same-sku.png')})
            self.assertEqual(edited.status_code, 200, edited.json)
        self.assertEqual(len(calls), 2)
        self.assertTrue(all(request.url.path == '/v1/images/edits' for request in calls))
        for run in (parent, edited.json['run_id']):
            response = client.get('/api/inspector/tasks/' + state['id'], query_string={
                'image_id': 'product_001', 'revision': 1, 'run_id': run})
            self.assertEqual(response.status_code, 200, response.json)
            graph = response.json['graph_view']
            self.assertEqual(graph['selection']['run_id'], run)
            self.assertEqual(len(graph['nodes']), 17)
            self.assertEqual(len(graph['edges']), 21)
            self.assertNotIn(CANARY, response.get_data(as_text=True))
        view = client.get('/api/inspector/tasks/' + state['id']).json
        self.assertEqual(view['selection']['run_id'], edited.json['run_id'])
        self.assertEqual(view['context_view']['cards'][4]['images'][-1]['role'], 'auxiliary_reference')
        self.assertTrue(all(self.files()[key] == value for key, value in before.items() if '/runs/' + parent + '/' in key))

    def test_read_only_is_explicit_mock_only_not_a_live_or_production_setting(self):
        for options in ({'execution_mode': 'LIVE DEBUG'}, {'execution_mode': 'MOCK', 'allow_paid_actions': True},
                        {'execution_mode': 'MOCK', 'allow_runtime_tasks': True}, {'execution_mode': 'MOCK', 'read_only_workspace': 'true'}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                app.create_local_debug_app(self.root, ['a' * 32], **{'read_only_workspace': True, **options})
        normal = app.create_app(self.root)
        self.assertEqual(len(list(normal.url_map.iter_rules())), 23)
        self.assertNotIn('匿名只读预览', normal.test_client().get('/').get_data(as_text=True))
        self.assertEqual(normal.test_client().get('/api/inspector/tasks').status_code, 404)


if __name__ == '__main__':
    unittest.main()
