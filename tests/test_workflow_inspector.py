"""Anonymous historical Evidence only; never a model call or real runtime read."""

import base64
import io
import json
from pathlib import Path
import subprocess
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from api.inspector import create_inspector_app
from image_workflow.inspector import InspectorError, InspectorReader
from file_ops import sha256


TASK = 'a' * 32
OTHER = 'b' * 32
CALL = 'c' * 32
RUN = '20261022T010000Z-' + 'd' * 32
FAILED = '20261022T020000Z-' + 'e' * 32
CANARY = 'sk-inspector-anonymous-canary-1234567890'


def make_evidence(root):
    """Two images, a saved Planning call, one Pass and one incomplete failed Run."""
    folder = Path(root) / 'sessions' / TASK
    def write(relative, value):
        path = folder / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False, indent=2).encode())
    assets = []
    raw_images = {}
    for identity, color in [('product_001', '#75a0b8'), ('reference_001', '#dcbf8e'), ('reference_002', '#b4a7cb')]:
        stream = io.BytesIO()
        Image.new('RGB', (180, 220), color).save(stream, 'PNG')
        raw = stream.getvalue()
        raw_images[identity] = raw
        write('inputs/' + identity + '.png', raw)
        assets.append({'id': identity, 'role': identity.split('_')[0], 'name': identity + '.png',
                       'file': 'inputs/' + identity + '.png', 'mime': 'image/png', 'sha256': sha256(raw)})
    texts = {'listing': '匿名商品来源陈述；参数待核验', 'description': '匿名商品外观依据', 'requirements': '保持外观，改善信息层级'}
    plans = {target: {'design': '仅使用本图对应设计参考，保持当前商品结构'} for target in ('reference_001', 'reference_002')}
    state = {'id': TASK, 'title': '匿名商品变形调查 · Mock Evidence', 'revision': 3, 'mode': 'product_pack',
             'images': assets, 'inputs': texts, 'plans': plans, 'product': {'appearance': '匿名候选理解，未经事实核验'},
             'references': {target: {'layout': '匿名设计方法'} for target in plans},
             'events': [{'action': 'understand', 'call_id': CALL, 'revision': 2}, {'action': 'confirm', 'target': 'reference_001', 'revision': 3}],
             'plan_confirmations': {'reference_001': {'revision': 3, 'plan_version': 1, 'source': 'EXPLICIT_PER_IMAGE'}}}
    write('state.json', state)
    write('versions/000003.json', state)
    write('inputs/texts.json', texts)
    result = {'product': state['product'], 'references': state['references'], 'plans': plans}
    call = 'calls/' + CALL + '/'
    write(call + 'run.json', {'id': CALL, 'session_id': TASK, 'parent_revision': 1, 'action': 'understand', 'status': 'AI_RESULT_RECEIVED', 'request_id': 'req_anonymous_planning'})
    write(call + 'request.json', {'model': 'offline-fixture', 'instructions': '匿名规则', 'input': [{'role': 'user', 'content': [
        {'type': 'input_text', 'text': '匿名输入 Context'},
        {'type': 'input_image', 'image_url': 'data:image/png;base64,' + base64.b64encode(raw_images['reference_001']).decode(), 'detail': 'auto'}]}]})
    write(call + 'image_order.json', [{'slot': i, **asset} for i, asset in enumerate(assets, 1)])
    write(call + 'prompt.txt', b'Anonymous planning prompt')
    write(call + 'response.json', {'output': result, 'usage': {'total_tokens': 30}})
    write(call + 'result.json', result)
    write(call + 'applied.json', {'run_id': CALL, 'parent_revision': 1, 'revision': 2, 'version_file': 'versions/000002.json'})
    for target, run_id, success in [('reference_001', RUN, True), ('reference_002', FAILED, False)]:
        prefix = f'generations/000003/{target}/runs/{run_id}/'
        chosen = [asset for asset in assets if asset['role'] == 'product' or asset['id'] == target]
        order = [{'slot': i, **asset} for i, asset in enumerate(chosen, 1)]
        context = {'session_id': TASK, 'confirmed_revision': 3, 'reference_id': target, 'original_inputs': texts,
                   'product_understanding': state['product'], 'reference_understanding': state['references'][target], 'confirmed_plan': plans[target]}
        record = {'run_id': run_id, 'session_id': TASK, 'reference_id': target, 'confirmed_revision': 3,
                  'version': 1, 'action': 'generate_image', 'parent_run_id': None, 'operation_id': ('1' if success else '2') * 32,
                  'model': 'offline-fixture', 'status': 'SUCCEEDED' if success else 'FAILED', 'api_call_attempted': True,
                  'inputs': order, 'elapsed_seconds': 2.4, 'api_elapsed_seconds': 2.1,
                  'request_id': 'req_anonymous_image' if success else None, 'usage': {'total_tokens': 30} if success else None,
                  'error': None if success else {'type': 'APIConnectionError', 'message': 'Anonymous failure ' + CANARY}}
        write(prefix + 'plan.json', context)
        for asset in chosen:
            write(prefix + asset['file'], raw_images[asset['id']])
        if success:
            output = io.BytesIO()
            Image.new('RGB', (240, 300), '#d2d8c1').save(output, 'PNG')
            raw = output.getvalue()
            record['output'] = {'file': 'image.png', 'sha256': sha256(raw), 'validated': True}
            write(prefix + 'image.png', raw)
            write(prefix + 'prompt.txt', b'Anonymous final prompt: preserve the original product.')
            write(prefix + 'request.json', {'model': 'offline-fixture', 'prompt': 'Anonymous final prompt: preserve the original product.', 'image_order': order, 'size': '240x300'})
            write(prefix + 'response.json', {'data': [{'b64_json': base64.b64encode(raw).decode()}], 'Authorization': CANARY,
                                           'output': [{'type': 'reasoning', 'content': 'HIDDEN_CANARY'}], 'usage': {'total_tokens': 30}})
        else:
            write(prefix + 'error.json', record['error'])
        write(prefix + 'run.json', record)
        write(f'generations/000003/{target}/current.json', {'latest_run': run_id, 'selected_run': run_id if success else None,
                                                          'passed_run': run_id if success else None, 'card_revision': 3})
    write('generations/000003/reference_001/reviews/' + 'f' * 32 + '.json',
          {'id': 'f' * 32, 'task_id': TASK, 'reference_id': 'reference_001', 'confirmed_revision': 3,
           'action': 'pass', 'run_id': RUN, 'version': 1})
    return folder


class WorkflowInspectorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'runtime'
        self.folder = make_evidence(self.root)
        self.reader = InspectorReader(self.root, [TASK])
        self.client = create_inspector_app(self.root, [TASK]).test_client()
        self.enterContext(patch('socket.socket.connect', side_effect=AssertionError('No network')))

    def url(self, run=RUN, target='reference_001'):
        return f'/api/inspector/tasks/{TASK}?image_id={target}&revision=3&run_id={run}'

    def fingerprint(self):
        return {str(path.relative_to(self.root)): (sha256(path.read_bytes()), path.stat().st_mtime_ns)
                for path in self.root.rglob('*') if path.is_file()}

    def test_success_has_explicit_graph_original_documents_images_and_pass(self):
        data = self.client.get(self.url()).json
        self.assertEqual(data['selection'], {'task_id': TASK, 'image_id': 'reference_001', 'revision': 3, 'run_id': RUN})
        self.assertEqual([node['id'] for node in data['nodes']], ['inputs', 'planning', 'confirmation', 'generation', 'review'])
        self.assertEqual(data['nodes'][1]['call_id'], CALL)
        self.assertEqual(data['edges'][1]['status'], 'INFERRED')
        self.assertEqual(data['edges'][-1]['status'], 'OBSERVED')
        self.assertTrue(all(item['hash_matches'] for item in data['assets']))
        self.assertEqual(data['nodes'][-1]['documents'][0]['data']['action'], 'pass')

    def test_partial_failed_run_shows_missing_response_prompt_and_real_error(self):
        data = self.client.get(self.url(FAILED, 'reference_002')).json
        docs = {doc['key']: doc for doc in data['nodes'][3]['documents']}
        self.assertEqual(docs['run.json']['data']['status'], 'FAILED')
        self.assertEqual(docs['response.json']['status'], 'MISSING')
        self.assertEqual(docs['prompt.txt']['status'], 'MISSING')
        self.assertEqual(docs['error.json']['data']['type'], 'APIConnectionError')
        self.assertEqual(data['nodes'][-1]['status'], 'MISSING')
        self.assertEqual(data['assets'][-1]['status'], 'MISSING')

    def test_gets_preview_only_saved_bytes_and_do_not_modify_evidence(self):
        before = self.fingerprint()
        data = self.client.get(self.url()).json
        query = f'?image_id=reference_001&revision=3&run_id={RUN}'
        for asset in data['assets']:
            response = self.client.get(f'/api/inspector/tasks/{TASK}/assets/{asset["key"]}' + query)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(sha256(response.data), asset['sha256'])
            self.assertEqual(response.mimetype, 'image/png')
            self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertEqual(self.client.get('/inspector').status_code, 200)
        self.assertEqual(self.fingerprint(), before)

    def test_response_strips_secrets_reasoning_and_image_encodings(self):
        for url in (self.url(), self.url(FAILED, 'reference_002')):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            text = response.get_data(as_text=True)
            self.assertNotIn(CANARY, text)
            self.assertNotIn('HIDDEN_CANARY', text)
            self.assertNotIn('iVBORw0KGgo', text)
            self.assertNotIn('data:image/png;base64,', text)
            self.assertIn('Content-Security-Policy', response.headers)

    def test_default_pilot_does_not_register_inspector_or_read_its_data(self):
        import app
        pilot = app.create_app(self.root, Path(self.temp.name) / 'case')
        self.assertEqual(pilot.test_client().get('/inspector').status_code, 404)
        self.assertEqual(pilot.test_client().get('/api/inspector/tasks').status_code, 404)
        self.assertEqual(len(list(pilot.url_map.iter_rules())), 23)

    def test_explicit_allowlist_is_required_and_foreign_tasks_fail_closed(self):
        for allowed in ([], ['*'], ['../' + TASK]):
            with self.assertRaises(InspectorError):
                create_inspector_app(self.root, allowed)
        self.assertEqual(self.client.get('/api/inspector/tasks').json['tasks'][0]['id'], TASK)
        foreign = self.root / 'sessions' / OTHER
        foreign.mkdir()
        (foreign / 'state.json').write_text(json.dumps({'id': OTHER, 'title': 'NOT_AUTHORIZED'}))
        response = self.client.get('/api/inspector/tasks/' + OTHER)
        self.assertEqual(response.status_code, 404)
        self.assertNotIn('NOT_AUTHORIZED', self.client.get('/api/inspector/tasks').get_data(as_text=True))

    def test_nonlocal_forwarded_cross_origin_and_host_rebinding_are_rejected(self):
        cases = [({'REMOTE_ADDR': '192.168.112.3'}, {}), ({}, {'Host': 'evil.example'}),
                 ({}, {'Origin': 'https://foreign.example'}), ({}, {'X-Forwarded-For': '127.0.0.1'}),
                 ({}, {'Forwarded': 'for=127.0.0.1'}), ({}, {'Sec-Fetch-Site': 'cross-site'})]
        for environment, headers in cases:
            with self.subTest(environment=environment, headers=headers):
                self.assertEqual(self.client.get(self.url(), environ_overrides=environment, headers=headers).status_code, 404)

    def test_no_debug_mutations_or_arbitrary_files_and_no_data_changes(self):
        before = self.fingerprint()
        for method in ('POST', 'PUT', 'PATCH', 'DELETE'):
            response = self.client.open(self.url(), method=method, headers={'X-Local-Action': 'prepare-plan'})
            self.assertEqual(response.status_code, 405)
        for url in ('/inspector-assets/app.py', '/api/sessions', '/api/case-001',
                    f'/api/inspector/tasks/{TASK}/assets/..%2F..%2F.env', self.url().replace('reference_001', 'reference_999'),
                    self.url().replace(RUN, FAILED), self.url().replace('revision=3', 'revision=../3')):
            self.assertEqual(self.client.get(url).status_code, 404, url)
        self.assertEqual(before, self.fingerprint())

    def test_tampered_paths_symlinks_and_foreign_run_identity_are_rejected(self):
        run_file = self.folder / f'generations/000003/reference_001/runs/{RUN}/run.json'
        original = json.loads(run_file.read_text())
        for changes in ({'session_id': OTHER}, {'inputs': [{'file': '../../.env'}]}):
            modified = {**original, **changes}
            run_file.write_text(json.dumps(modified))
            if 'inputs' in changes:
                request_file = run_file.parent / 'request.json'
                request_file.unlink()
            self.assertEqual(self.client.get(self.url()).status_code, 404)
        run_file.write_text(json.dumps(original))
        image = self.folder / 'inputs/product_001.png'
        image.unlink()
        image.symlink_to(self.folder / 'inputs/reference_001.png')
        self.assertEqual(self.client.get(self.url()).status_code, 404)

    def test_missing_snapshot_is_not_reconstructed_from_current_state(self):
        (self.folder / 'versions/000003.json').unlink()
        data = self.client.get(self.url()).json
        self.assertEqual(data['nodes'][2]['status'], 'MISSING')
        self.assertIsNone(data['nodes'][2]['documents'][0]['data'])
        self.assertEqual(data['edges'][2]['status'], 'MISSING')
        self.assertEqual(data['nodes'][1]['status'], 'MISSING')

    def test_hash_mismatch_is_visible_without_modifying_recorded_hash(self):
        path = self.folder / 'inputs/product_001.png'
        old_hash = sha256(path.read_bytes())
        path.write_bytes((self.folder / 'inputs/reference_001.png').read_bytes())
        data = self.client.get(self.url()).json
        asset = next(item for item in data['assets'] if item['key'] == 'original-0')
        self.assertFalse(asset['hash_matches'])
        self.assertEqual(asset['expected_sha256'], old_hash)

    def test_quick_mode_marks_planning_not_applicable_without_inventing_a_plan(self):
        path = self.folder / 'state.json'
        state = json.loads(path.read_text())
        state['mode'] = 'quick_redesign'
        path.write_text(json.dumps(state))
        data = self.reader.inspect(TASK)
        self.assertEqual(data['selection']['image_id'], 'product_001')
        self.assertFalse(data['nodes'][1]['applicable'])
        self.assertEqual(data['nodes'][1]['documents'], [])
        self.assertEqual(data['edges'][0]['source'], 'inputs')
        self.assertEqual(data['edges'][0]['target'], 'generation')

    def test_corrupt_document_is_missing_with_original_hash_not_raw_content(self):
        path = self.folder / f'generations/000003/reference_001/runs/{RUN}/response.json'
        path.write_bytes(('not-json ' + CANARY).encode())
        data = self.client.get(self.url()).json
        doc = next(doc for doc in data['nodes'][3]['documents'] if doc['key'] == 'response.json')
        self.assertEqual(doc['status'], 'MISSING')
        self.assertEqual(doc['sha256'], sha256(path.read_bytes()))
        self.assertNotIn(CANARY, json.dumps(data))

    def test_historical_revision_and_run_selection_do_not_follow_current_pointer(self):
        card = self.folder / 'generations/000003/reference_001'
        second = '20261022T030000Z-' + '9' * 32
        shutil.copytree(card / 'runs' / RUN, card / 'runs' / second)
        path = card / 'runs' / second / 'run.json'
        record = json.loads(path.read_text())
        record.update(run_id=second, version=2, parent_run_id=RUN, feedback='匿名局部修改意见')
        path.write_text(json.dumps(record))
        current = json.loads((self.folder / 'state.json').read_text())
        current['revision'] = 4
        (self.folder / 'state.json').write_text(json.dumps(current))
        (self.folder / 'versions/000004.json').write_text(json.dumps(current))
        before = self.fingerprint()
        chosen = self.reader.inspect(TASK, 'reference_001', 3, second)
        self.assertEqual(chosen['revisions'], [4, 3])
        self.assertEqual(chosen['runs'], [second, RUN])
        self.assertEqual(chosen['nodes'][3]['documents'][0]['data']['parent_run_id'], RUN)
        self.assertEqual(chosen['nodes'][4]['status'], 'MISSING')  # V1 Pass is never V2 Pass.
        fresh = self.reader.inspect(TASK, 'reference_001', 4)
        self.assertEqual(fresh['nodes'][3]['status'], 'MISSING')
        self.assertIsNone(fresh['selection']['run_id'])
        self.assertEqual(before, self.fingerprint())

    def test_foreign_planning_and_review_records_are_not_displayed(self):
        call = self.folder / f'calls/{CALL}/run.json'
        original = call.read_bytes()
        call.write_text(json.dumps({'session_id': OTHER, 'content': 'NOT_AUTHORIZED'}))
        self.assertEqual(self.client.get(self.url()).status_code, 404)
        call.write_bytes(original)
        event = self.folder / ('generations/000003/reference_001/reviews/' + 'f' * 32 + '.json')
        data = json.loads(event.read_text())
        data['task_id'] = OTHER
        event.write_text(json.dumps(data))
        response = self.client.get(self.url())
        self.assertEqual(response.status_code, 404)
        self.assertNotIn('NOT_AUTHORIZED', response.get_data(as_text=True))

    def test_asset_defaults_and_invalid_image_bytes_are_safe(self):
        self.assertEqual(self.client.get(f'/api/inspector/tasks/{TASK}/assets/output').status_code, 200)
        path = self.folder / f'generations/000003/reference_001/runs/{RUN}/image.png'
        path.write_bytes(b'not an image')
        self.assertEqual(self.client.get(f'/api/inspector/tasks/{TASK}/assets/output').status_code, 404)

    def test_cli_help_and_fresh_factory_import_do_not_load_models_or_read_data(self):
        script = """
import importlib.abc,sys
from pathlib import Path
class Block(importlib.abc.MetaPathFinder):
 def find_spec(self,name,*args):
  if name.split('.')[0] in {'openai','app','prepare_plan','cli'} or name.startswith(('image_workflow.planning','image_workflow.generation','image_workflow.tasks','image_workflow.review')):
   raise AssertionError('Model or workflow imported: '+name)
sys.meta_path.insert(0,Block())
sys.path.insert(0,sys.argv[1])
from api.inspector import create_inspector_app
app=create_inspector_app(Path(sys.argv[2])/'does-not-exist',['a'*32])
assert not (Path(sys.argv[2])/'does-not-exist').exists()
assert app.test_client().get('/inspector').status_code==200
"""
        result = subprocess.run([sys.executable, '-B', '-c', script, str(Path(__file__).resolve().parents[1] / 'src'), self.temp.name],
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        help_result = subprocess.run([sys.executable, '-B', '-m', 'api.inspector', '--help'],
                                     cwd=Path(__file__).resolve().parents[1] / 'src', capture_output=True, text=True, timeout=15)
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        self.assertIn('--task-id', help_result.stdout)


if __name__ == '__main__':
    unittest.main()
