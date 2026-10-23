"""V0.6: actual Quick workflow writes, anonymous SDK Mock only, read-only projection."""

import base64
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

import httpx
from openai import OpenAI
from PIL import Image, ImageDraw

import app
from file_ops import sha256
from image_workflow.tasks import generation_runtime


HEADERS = {'X-Local-Action': 'prepare-plan'}
CANARY = 'sk-anonymous-v06-offline-canary-1234567890'


def anonymous_image(kind='original'):
    """Clearly synthetic product diagrams; no real product or model output."""
    output = io.BytesIO()
    generated = kind == 'output'
    image = Image.new('RGB', (1024, 1536) if generated else (320, 420), '#eaf1f6')
    draw = ImageDraw.Draw(image)
    width, height = image.size
    if kind == 'reference':
        draw.rectangle((18, 18, width - 18, height - 18), fill='#e5d9ca')
        draw.rectangle((35, 80, 145, 310), fill='#6f8193')
        for y in (95, 150, 205):
            draw.rectangle((175, y, 280, y + 16), fill='#ffffff')
    else:
        left, right = int(width * .28), int(width * .69)
        draw.rounded_rectangle((left, height * .24, right, height * .79), radius=int(width * .06), fill='#477d9c')
        draw.rounded_rectangle((width * .4, height * .13, width * .57, height * .28), radius=10, fill='#203f52')
        draw.rectangle((left + 10, height * .43, right - 10, height * .60), fill='#f6fafc')
        if generated:
            draw.rectangle((80, 85, 940, 100), fill='#477d9c')
            draw.text((80, 120), 'ANONYMOUS MOCK OUTPUT - NOT A REAL MODEL RESULT', fill='#203f52')
    draw.text((14, height - 28), 'ANONYMOUS / ' + kind.upper(), fill='#203f52')
    image.save(output, 'PNG')
    return output.getvalue()


def mock_client(requests, *, failure=False):
    def transport(request):
        requests.append(request)
        if failure:
            return httpx.Response(401, json={'error': {'message': 'Anonymous invalid key', 'type': 'invalid_api_key'}})
        return httpx.Response(200, json={'data': [{'b64_json': base64.b64encode(anonymous_image('output')).decode()}],
            'usage': {'input_tokens': 12, 'output_tokens': 18, 'total_tokens': 30}},
            headers={'x-request-id': 'req_anonymous_v06_mock'})
    return patch.object(generation_runtime, 'make_client', side_effect=lambda key:
        OpenAI(api_key=key, max_retries=0, http_client=httpx.Client(transport=httpx.MockTransport(transport))))


def make_quick_evidence(root, *, failure=False):
    """One explicit offline HTTP generation produces the saved Evidence under test."""
    application = app.create_app(root)
    state = application.extensions['plan_store'].create({
        'listing': '匿名来源文字；不自动作为 Quick Prompt 内容。',
        'description': '匿名商品描述，仅存入资料快照。',
        'requirements': '蓝白配色，改善信息层级，保留原商品外观。',
        'product_facts': '匿名蓝色瓶体与深色盖；不得增加配件或参数。'},
        [('product', 'anonymous-original.png', anonymous_image()),
         ('reference', 'anonymous-style.png', anonymous_image('reference'))],
        'V0.6 Anonymous Quick · SDK Mock Evidence', mode='quick_redesign')
    requests = []
    with patch.dict(os.environ, {'OPENAI_API_KEY': CANARY, 'OPENAI_IMAGE_MODEL': 'gpt-image-2.5-sunburst'}), mock_client(requests, failure=failure):
        response = application.test_client().post('/api/sessions/' + state['id'] + '/generate/product_001',
            headers=HEADERS, json={'confirmed_revision': state['revision'], 'card_revision': 0, 'operation_id': uuid4().hex})
    assert response.status_code == (502 if failure else 200), response.json
    return application, state, response.json['run_id'], requests


class ContextInspectorTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / 'anonymous-runtime'
        self.enterContext(patch('socket.socket.connect', side_effect=AssertionError('No network')))
        self.business, self.state, self.run, self.requests = make_quick_evidence(self.root)
        self.debug = app.create_local_debug_app(self.root, [self.state['id']], execution_mode='MOCK')
        self.client = self.debug.test_client()
        self.url = '/api/inspector/tasks/' + self.state['id']
        self.run_root = self.root / 'sessions' / self.state['id'] / 'generations/000001/product_001/runs' / self.run

    def get(self):
        result = self.client.get(self.url, query_string={'image_id': 'product_001', 'revision': 1, 'run_id': self.run})
        self.assertEqual(result.status_code, 200, result.json)
        return result.json

    def card(self, name, view=None):
        return next(card for card in (view or self.get())['context_view']['cards'] if card['id'] == name)

    def fingerprint(self):
        return {str(p.relative_to(self.root)): (sha256(p.read_bytes()), p.stat().st_mtime_ns)
                for p in self.root.rglob('*') if p.is_file()}

    def test_actual_quick_request_is_projected_with_roles_order_prompt_and_exact_sources(self):
        view = self.get()
        context = view['context_view']
        self.assertEqual(len(self.requests), 1)
        self.assertTrue(context['supported'])
        self.assertEqual([item['id'] for item in context['cards']], ['product', 'references', 'requirements', 'assembly', 'request', 'output'])
        images = self.card('request', view)['images']
        self.assertEqual([(item['position'], item['slot'], item['id'], item['role']) for item in images],
                         [(1, 1, 'product_001', 'original'), (2, 2, 'reference_001', 'design_reference')])
        self.assertTrue(all(item['hash_matches'] for item in images))
        self.assertEqual(images[1]['sources'][0]['pointer'], '/image_order/1')
        request = json.loads((self.run_root / 'request.json').read_text())
        self.assertEqual(context['prompt']['value'], request['prompt'])
        self.assertEqual(context['prompt']['sources'][0]['sha256'], sha256((self.run_root / 'request.json').read_bytes()))
        checks = {item['label']: item['result'] for item in self.card('assembly', view)['checks']}
        self.assertEqual(checks['本次整体设计要求 → 请求标签'], 'MATCH')
        self.assertEqual(checks['运营提供的商品事实约束 → 请求标签'], 'MATCH')
        self.assertEqual(checks['本次修改意见 → 请求标签'], 'UNKNOWN')
        self.assertEqual(checks['request.prompt 与 prompt.txt'], 'MATCH')
        self.assertEqual(checks['输入图片记录哈希与本次文件'], 'MATCH')
        self.assertNotIn(self.state['inputs']['description'], context['prompt']['value'])
        self.assertIn('不代表此字段原样发送', self.card('product', view)['fields'][1]['note'])
        self.assertEqual(view['nodes'][1]['status'], 'NOT_APPLICABLE')

    def test_context_assets_comparison_and_raw_evidence_are_read_only_and_sanitized(self):
        before = self.fingerprint()
        view = self.get()
        comparison = view['context_view']['comparison']
        self.assertEqual(comparison, {'before': 'run-input-0', 'after': 'output'})
        for key in (comparison['before'], comparison['after'], 'run-input-1'):
            image = self.client.get(self.url + '/assets/' + key, query_string=view['selection'])
            self.assertEqual(image.status_code, 200)
            asset = next(asset for asset in view['assets'] if asset['key'] == key)
            self.assertEqual(sha256(image.data), asset['sha256'])
        page = self.client.get('/inspector').get_data(as_text=True)
        self.assertIn('高级证据', page)
        self.assertIn('<details id="advanced-evidence"', page)
        self.assertNotIn('<details id="advanced-evidence" open', page)
        text = json.dumps(view)
        for hidden in (CANARY, 'iVBORw0KGgo', 'data:image/png;base64,'):
            self.assertNotIn(hidden, text)
        self.assertEqual(self.fingerprint(), before)
        self.assertEqual(len(self.requests), 1)

    def test_missing_request_is_not_fabricated_from_run_or_current_code(self):
        (self.run_root / 'request.json').unlink()
        context = self.get()['context_view']
        self.assertEqual(context['prompt']['status'], 'UNKNOWN')
        self.assertEqual(context['prompt_file']['status'], 'OBSERVED')
        request = next(card for card in context['cards'] if card['id'] == 'request')
        self.assertEqual(request['fields'][0]['status'], 'UNKNOWN')  # Run.model is not request.model.
        self.assertEqual(request['images'][0]['sources'][0]['document_key'], 'run.json')
        self.assertIn('UNKNOWN', request['images'][0]['note'])
        self.assertEqual(self.card('assembly')['checks'][0]['result'], 'UNKNOWN')

    def test_missing_context_never_falls_back_to_todays_task_or_original_texts(self):
        (self.run_root / 'plan.json').unlink()
        context = self.card('requirements')
        self.assertEqual(context['fields'][0]['status'], 'UNKNOWN')
        self.assertIsNone(context['fields'][0]['value'])
        self.assertEqual(self.get()['context_view']['prompt']['status'], 'OBSERVED')

    def test_missing_all_image_manifests_does_not_promote_task_references_to_actual_inputs(self):
        (self.run_root / 'request.json').unlink()
        path = self.run_root / 'run.json'
        record = json.loads(path.read_text())
        record.pop('inputs')
        path.write_text(json.dumps(record))
        view = self.get()
        self.assertEqual(self.card('request', view)['images'], [])
        self.assertIn('UNKNOWN', self.card('request', view)['summary'])
        self.assertEqual(self.card('references', view)['images'], [])
        self.assertIn('UNKNOWN', self.card('references', view)['summary'])
        product = self.card('product', view)['images'][0]
        self.assertTrue(product['asset_key'].startswith('original-'))
        self.assertIn('是否实际发送 UNKNOWN', product['note'])

    def test_historical_values_do_not_follow_current_task_changes(self):
        store = self.business.extensions['plan_store']
        current = store.load(self.state['id'])
        current['inputs']['requirements'] = 'TODAYS_REQUIREMENTS_NOT_SENT'
        store.save(current, {'action': 'anonymous_input_update'})
        view = self.get()
        self.assertEqual(self.card('requirements', view)['fields'][0]['value'], self.state['inputs']['requirements'])
        self.assertNotIn('TODAYS_REQUIREMENTS_NOT_SENT', json.dumps(view['context_view']))

    def test_mismatched_context_identity_is_unknown_and_has_a_visible_warning(self):
        path = self.run_root / 'plan.json'
        context = json.loads(path.read_text())
        context['source_image_id'] = 'product_999'
        path.write_text(json.dumps(context))
        view = self.get()
        self.assertTrue(view['context_view']['warnings'])
        self.assertEqual(self.card('requirements', view)['fields'][0]['status'], 'UNKNOWN')

    def test_prompt_and_image_hash_mismatches_are_observed_without_repair(self):
        (self.run_root / 'prompt.txt').write_text('Different anonymous prompt')
        (self.run_root / 'inputs/product_001.png').write_bytes(anonymous_image('reference'))
        before = self.fingerprint()
        view = self.get()
        checks = {item['label']: item['result'] for item in self.card('assembly', view)['checks']}
        self.assertEqual(checks['request.prompt 与 prompt.txt'], 'MISMATCH')
        self.assertEqual(checks['Prompt 文件与 Run 记录哈希'], 'MISMATCH')
        self.assertEqual(checks['输入图片记录哈希与本次文件'], 'MISMATCH')
        self.assertEqual(self.fingerprint(), before)

    def test_saved_array_order_is_preserved_and_slot_disagreement_is_flagged(self):
        path = self.run_root / 'request.json'
        request = json.loads(path.read_text())
        request['image_order'].reverse()
        path.write_text(json.dumps(request))
        view = self.get()
        self.assertEqual([item['slot'] for item in self.card('request', view)['images']], [2, 1])
        self.assertTrue(view['context_view']['warnings'])
        self.assertEqual(next(check for check in self.card('assembly', view)['checks'] if check['label'] == 'request.image_order 与 Run.inputs')['result'], 'MISMATCH')

    def test_edit_uses_saved_parent_auxiliary_role_and_feedback_not_shared_history(self):
        with patch.dict(os.environ, {'OPENAI_API_KEY': CANARY}), mock_client(self.requests):
            edited = self.business.test_client().post('/api/sessions/' + self.state['id'] + '/revise/product_001',
                headers=HEADERS, data={'confirmed_revision': '1', 'card_revision': '2', 'parent_run_id': self.run,
                    'operation_id': uuid4().hex, 'feedback': '仅修正瓶盖颜色，不改变文字。', 'auxiliary_purpose': 'product_appearance',
                    'auxiliary': (io.BytesIO(anonymous_image()), 'same-sku.png')})
        self.assertEqual(edited.status_code, 200, edited.json)
        self.run = edited.json['run_id']
        view = self.get()
        self.assertEqual([item['role'] for item in self.card('request', view)['images']],
                         ['current_image', 'original', 'design_reference', 'auxiliary_reference'])
        self.assertEqual(view['context_view']['comparison']['before'], 'run-input-1')
        fields = self.card('references', view)['fields']
        self.assertEqual(fields[1]['value'], '商品外观修正')
        self.assertEqual(fields[2]['value'], 'current_image_only')
        self.assertEqual(next(item for item in self.card('assembly', view)['checks'] if item['label'] == '本次修改意见 → 请求标签')['result'], 'MATCH')

    def test_failed_run_and_missing_images_do_not_invent_model_output(self):
        _, state, run, _ = make_quick_evidence(self.root, failure=True)
        failed = self.client.get('/api/inspector/tasks/' + state['id'])
        self.assertEqual(failed.status_code, 404)  # Existing static task scope stays enforced.
        reader = app.create_local_debug_app(self.root, [state['id']], execution_mode='MOCK').test_client()
        view = reader.get('/api/inspector/tasks/' + state['id']).json
        self.assertEqual(view['selection']['run_id'], run)
        self.assertEqual(self.card('output', view)['images'][0]['status'], 'MISSING')
        self.assertEqual(self.card('output', view)['fields'][0]['value'], 'FAILED')
        self.assertEqual(self.card('output', view)['fields'][3]['value'], 'AuthenticationError')


if __name__ == '__main__':
    unittest.main()
