"""CP1 business relations: anonymous temporary tasks and real SDK serialization.

No production runtime, real credentials, network, Planning or visual acceptance.
"""

import base64
import copy
from email.parser import BytesParser
import io
import json
import threading
import unittest
from unittest.mock import patch
from uuid import uuid4
import zipfile

import httpx
from PIL import Image

import test_generate_plan_image as fixtures
from image_workflow.generation import quick_v1


def picture(color, size=(32, 40)):
    data = io.BytesIO()
    Image.new('RGB', size, color).save(data, 'PNG')
    return data.getvalue()


def slots():
    return [
        {'id': 'reference_101', 'type': 'main', 'enabled': True, 'reference_id': 'reference_001'},
        {'id': 'reference_102', 'type': 'dimensions', 'enabled': True, 'reference_id': 'reference_002',
         'requirements': '只表达自家尺寸图中有依据的尺寸'},
        {'id': 'reference_103', 'type': 'scene', 'enabled': True, 'reference_id': 'reference_003'},
        {'id': 'reference_104', 'type': 'comparison', 'enabled': False, 'reference_id': None},
    ]


class QuickV1Tests(unittest.TestCase):
    def setUp(self):
        self.fx = fixtures.GenerationPageTests()
        self.fx.setUp()
        self.addCleanup(self.fx.doCleanups)
        self.client, self.store = self.fx.client, self.fx.store
        self.enterContext(patch('socket.socket.connect', side_effect=AssertionError('No network')))
        self.enterContext(patch.object(fixtures.web, 'call_ai', side_effect=AssertionError('No Planning')))
        self.sources = [picture(color) for color in ('white', 'blue', 'green', 'yellow')]
        self.references = [picture(color) for color in ('red', 'orange', 'purple', 'black')]
        response = self.create()
        self.assertEqual(response.status_code, 200, response.json)
        self.state = response.json['state']
        self.folder = self.store.folder(self.state['id'])

    def create(self, *, configuration=None, count=3, **extra):
        form = {'title': 'Anonymous CP1 same SKU', 'mode': 'quick_redesign',
                'quick_business_version': 'v1', 'quick_slots': json.dumps(slots() if configuration is None else configuration),
                'requirements': '蓝白风格；只制作主动选择的图位', 'product_facts': '不得增加配件',
                'product': [(io.BytesIO(data), name) for data, name in zip(self.sources[:count],
                    ('white-background.png', 'dimensions.png', 'detail.png', 'extra-detail.png'))],
                # The fourth reference is intentionally unbound: V1 must not
                # inherit it as a global style image.
                'reference': [(io.BytesIO(data), f'ref-{i}.png') for i, data in enumerate(self.references)], **extra}
        return self.client.post('/api/sessions', headers=fixtures.HEADERS, data=form)

    def cards(self, state=None):
        result = self.client.get(f"/api/sessions/{(state or self.state)['id']}/generation")
        self.assertEqual(result.status_code, 200, result.json)
        return result.json['cards']

    def card(self, target='reference_101', state=None):
        return next(card for card in self.cards(state) if card['id'] == target)

    def generate(self, target='reference_101', state=None, operation=None, revision=None, **extra):
        state = state or self.state
        card = self.card(target, state)
        return self.client.post(f"/api/sessions/{state['id']}/generate/{target}", headers=fixtures.HEADERS,
            json={'confirmed_revision': state['revision'], 'card_revision': card['card_revision'] if revision is None else revision,
                  'operation_id': operation or uuid4().hex, **extra})

    def edit(self, target='reference_101', parent=None, auxiliary=None, operation=None, state=None):
        state = state or self.state
        card = self.card(target, state)
        body = {'confirmed_revision': state['revision'], 'card_revision': card['card_revision'],
                'parent_run_id': parent or card['selected_run'], 'operation_id': operation or uuid4().hex,
                'feedback': '只修正当前图片的背景，保留商品身份'}
        url = f"/api/sessions/{state['id']}/revise/{target}"
        if auxiliary is None:
            return self.client.post(url, headers=fixtures.HEADERS, json=body)
        return self.client.post(url, headers=fixtures.HEADERS, data={**{k: str(v) for k, v in body.items()},
            'auxiliary': (io.BytesIO(auxiliary), 'correction.png'), 'auxiliary_purpose': 'product_appearance'})

    def review(self, kind, run, target='reference_101'):
        return self.client.post(f"/api/sessions/{self.state['id']}/review/{target}", headers=fixtures.HEADERS,
            json={'confirmed_revision': self.state['revision'], 'card_revision': self.card(target)['card_revision'],
                  'action': kind, 'run_id': run})

    def run_folder(self, run, target='reference_101', state=None):
        state = state or self.state
        return self.fx.app.extensions['generation_service'].run_folder(state['id'], state['revision'], target, run)

    def request_parts(self):
        request = self.fx.requests[-1]
        message = BytesParser().parsebytes(('Content-Type: ' + request.headers['content-type'] + '\r\n\r\n').encode() + request.read())
        return message.get_payload()

    def test_three_enabled_slots_are_stable_and_not_product_count(self):
        self.assertEqual(self.state['quick_business_version'], 'v1')
        self.assertEqual(self.state['plans'], {})
        self.assertFalse(self.state['confirmed'])
        self.assertEqual([c['id'] for c in self.cards()], ['reference_101', 'reference_102', 'reference_103'])
        for card, reference in zip(self.cards(), ('reference_001', 'reference_002', 'reference_003')):
            self.assertEqual(card['output_slot']['reference_id'], reference)
            self.assertTrue(card['reference']['url'].endswith('/images/' + reference))
            self.assertEqual(card['style_references'], [])
        fourth = self.create(count=4).json['state']
        self.assertEqual([c['id'] for c in self.cards(fourth)], [c['id'] for c in self.cards()])
        reloaded = fixtures.web.create_app(self.fx.runtime).test_client()
        self.assertEqual(reloaded.get(f"/api/sessions/{self.state['id']}").json['state']['quick_slots'], self.state['quick_slots'])
        self.assertEqual(self.fx.requests, [])

    def test_sdk_wire_has_all_three_product_bytes_and_only_bound_reference(self):
        with self.fx.with_sdk():
            result = self.generate('reference_102')
        self.assertEqual(result.status_code, 200, result.json)
        parts = self.request_parts()
        image_parts = [part for part in parts if part.get_filename()]
        self.assertEqual([part.get_filename() for part in image_parts],
                         ['product_001.png', 'product_002.png', 'product_003.png', 'reference_002.png'])
        self.assertEqual([part.get_payload(decode=True) for part in image_parts], self.sources[:3] + [self.references[1]])
        folder = self.run_folder(result.json['run_id'], 'reference_102')
        request = json.loads((folder/'request.json').read_text())
        context = json.loads((folder/'plan.json').read_text())
        record = json.loads((folder/'run.json').read_text())
        self.assertEqual([i['role'] for i in request['image_order']], ['product', 'product', 'product', 'design_reference'])
        self.assertEqual([i['slot'] for i in request['image_order']], [1, 2, 3, 4])
        for image, payload in zip(request['image_order'], image_parts):
            data = payload.get_payload(decode=True)
            self.assertEqual((folder/image['file']).read_bytes(), data)
            self.assertEqual(image['sha256'], fixtures.generation.sha256(data))
        prompt = next(p.get_payload(decode=True).decode() for p in parts if p.get_param('name', header='content-disposition') == 'prompt')
        self.assertEqual(prompt, request['prompt'])
        self.assertEqual(prompt, (folder/'prompt.txt').read_text())
        self.assertIn(self.state['quick_slots'][1]['requirements'], prompt)
        self.assertIn(self.state['inputs']['requirements'], prompt)
        self.assertIn('尺寸图', prompt)
        self.assertNotIn('confirmed_plan', context)
        self.assertNotIn('source_image_id', context)
        self.assertNotIn('source_image_id', record)
        self.assertEqual(context['output_id'], 'reference_102')
        self.assertEqual(request['output_slot'], record['output_slot'])
        self.assertEqual(context['output_slot'], record['output_slot'])
        self.assertEqual((record['model'], record['max_retries'], record['timeout_seconds']), ('gpt-image-2.5-sunburst', 0, 180.0))

    def test_empty_optional_requirements_use_type_goal_without_planning(self):
        with self.fx.with_sdk():
            result = self.generate()
        self.assertEqual(result.status_code, 200, result.json)
        prompt = json.loads((self.run_folder(result.json['run_id'])/'request.json').read_text())['prompt']
        self.assertIn('清楚展示实际售卖商品', prompt)
        self.assertNotIn('不是白底主图模式', prompt)
        self.assertEqual(len(self.fx.requests), 1)

    def test_server_rejects_unknown_versions_and_does_not_infer_from_slots(self):
        for extra in ({'quick_business_version': 'future'}, {'quick_business_version': ''},
                      {'quick_business_version': 'legacy'}, {'mode': 'product_pack'}):
            with self.subTest(extra=extra):
                self.assertEqual(self.create(**extra).status_code, 400)
        missing_version = {'title': 'No inferred version', 'mode': 'quick_redesign',
                           'quick_slots': json.dumps(slots()),
                           'product': (io.BytesIO(self.sources[0]), 'anonymous.png')}
        self.assertEqual(self.client.post('/api/sessions', headers=fixtures.HEADERS, data=missing_version).status_code, 400)
        self.assertEqual(self.create(quick_slots='malformed JSON').status_code, 400)
        legacy = self.store.create({'listing': '', 'description': '', 'requirements': 'legacy'},
            [('product', 'old.png', self.sources[0])], 'Old Quick', mode='quick_redesign')
        legacy['quick_slots'] = self.state['quick_slots']
        self.assertFalse(quick_v1.is_v1(legacy))
        self.assertEqual(self.fx.app.extensions['generation_service'].targets(legacy), ['product_001'])
        self.assertEqual(self.fx.requests, [])

    def test_invalid_and_foreign_reference_forms_are_rejected_before_task_writes(self):
        other = self.create().json['state']
        foreign_folder = self.store.folder(other['id'])
        foreign_before = {p:p.read_bytes() for p in foreign_folder.rglob('*') if p.is_file()}
        cases = []
        for reference in ('product_001', 'reference_999', '../reference_001', other['id'] + '/reference_001', None):
            config = slots(); config[0]['reference_id'] = reference; cases.append(config)
        config = slots(); config[0]['reference_task_id'] = 'b'*32; cases.append(config)
        config = slots(); config[1]['reference_id'] = config[0]['reference_id']; cases.append(config)
        config = slots(); config[0]['id'] = '../reference_101'; cases.append(config)
        config = slots(); config[1]['id'] = config[0]['id']; cases.append(config)
        before = sorted(p.name for p in (self.store.root/'sessions').iterdir())
        for config in cases:
            with self.subTest(config=config):
                self.assertEqual(self.create(configuration=config).status_code, 400)
        self.assertEqual(sorted(p.name for p in (self.store.root/'sessions').iterdir()), before)
        self.assertEqual({p:p.read_bytes() for p in foreign_folder.rglob('*') if p.is_file()}, foreign_before)
        self.assertEqual(self.fx.requests, [])

    def test_types_enabled_flags_and_each_slot_cap_are_enforced(self):
        for kind, (limit, _, _) in quick_v1.SLOT_TYPES.items():
            config = [{'id': f'reference_{i+101:03}', 'type': kind, 'enabled': False} for i in range(limit+1)]
            with self.subTest(kind=kind):
                self.assertEqual(self.create(configuration=config).status_code, 400)
        for config in ([], slots()*3, {}, [{'id':'reference_101','type':'video','enabled':True}],
                       [{'id':'reference_101','type':'main','enabled':'true','reference_id':'reference_001'}]):
            self.assertEqual(self.create(configuration=config).status_code, 400)
        full = []
        for kind, (limit, _, _) in quick_v1.SLOT_TYPES.items():
            full.extend({'id':f'reference_{len(full)+i+201:03}', 'type':kind, 'enabled':False} for i in range(limit))
        self.assertEqual(len(full), 8)
        self.assertEqual(self.create(configuration=full).status_code, 200)

    def test_disabled_and_product_targets_cannot_generate_or_batch(self):
        for target in ('reference_104', 'product_001', 'reference_004'):
            result = self.client.post(f"/api/sessions/{self.state['id']}/generate/{target}", headers=fixtures.HEADERS,
                json={'confirmed_revision':1, 'card_revision':0, 'operation_id':uuid4().hex, 'batch_only':True})
            self.assertEqual(result.status_code, 404)
        self.assertFalse((self.folder/'generations').exists())
        self.assertEqual(self.fx.requests, [])

    def test_immutable_snapshot_and_copy_require_explicit_version_and_new_bindings(self):
        before = {p:p.read_bytes() for p in self.folder.rglob('*') if p.is_file()}
        form = {'title':'copy', 'mode':'quick_redesign', 'from_session':self.state['id'],
                'keep_images':json.dumps([i['id'] for i in self.state['images']])}
        self.assertEqual(self.client.post('/api/sessions', headers=fixtures.HEADERS, data=form).status_code, 400)
        form.update(quick_business_version='v1', quick_slots=json.dumps(self.state['quick_slots']))
        copied = self.client.post('/api/sessions', headers=fixtures.HEADERS, data=form)
        self.assertEqual(copied.status_code, 200, copied.json)
        self.assertNotEqual(copied.json['state']['id'], self.state['id'])
        self.assertEqual(copied.json['state']['quick_slots'], self.state['quick_slots'])
        self.assertEqual({p:p.read_bytes() for p in self.folder.rglob('*') if p.is_file()}, before)

    def test_edit_preserves_parent_all_product_inputs_binding_and_auxiliary(self):
        with self.fx.with_sdk():
            first = self.generate().json['run_id']
            result = self.edit(auxiliary=picture('cyan'))
        self.assertEqual(result.status_code, 200, result.json)
        folder = self.run_folder(result.json['run_id'])
        record = json.loads((folder/'run.json').read_text())
        request = json.loads((folder/'request.json').read_text())
        self.assertEqual(record['parent_run_id'], first)
        self.assertEqual(record['reference_id'], 'reference_101')
        self.assertEqual(record['output_slot']['reference_id'], 'reference_001')
        self.assertEqual([i['id'] for i in request['image_order']],
            ['current_image', 'product_001', 'product_002', 'product_003', 'reference_001', 'auxiliary_reference'])
        self.assertEqual([i['role'] for i in request['image_order']],
            ['current_image', 'product', 'product', 'product', 'design_reference', 'auxiliary_reference'])
        self.assertEqual((folder/'inputs/current_image.png').read_bytes(), (self.run_folder(first)/'image.png').read_bytes())
        self.assertEqual((folder/'inputs/auxiliary_reference.png').read_bytes(), picture('cyan'))
        self.assertIn(record['feedback'], request['prompt'])
        self.assertEqual([c['status'] for c in self.cards()], ['SUCCEEDED', 'NOT_STARTED', 'NOT_STARTED'])

    def test_other_output_and_other_task_parent_runs_are_refused(self):
        other = self.create().json['state']
        with self.fx.with_sdk():
            parent = self.generate().json['run_id']
            foreign = self.generate(state=other).json['run_id']
            self.assertEqual(self.edit(target='reference_102', parent=parent).status_code, 409)
            self.assertEqual(self.edit(parent=foreign).status_code, 409)
        self.assertEqual(len(self.fx.requests), 2)

    def test_pass_versions_both_zips_and_restart_keep_output_identity(self):
        with self.fx.with_sdk():
            first = self.generate().json['run_id']
            self.assertEqual(self.review('pass', first).status_code, 200)
            revised = self.edit().json['run_id']
        first_bytes = (self.run_folder(first)/'image.png').read_bytes()
        self.assertEqual(self.card()['passed_run'], first)
        self.assertEqual(self.card()['selected_run'], revised)
        self.assertEqual(len(self.card()['versions']), 2)
        restarted = fixtures.web.create_app(self.fx.runtime).test_client()
        self.assertEqual(restarted.get(f"/api/sessions/{self.state['id']}/generation").json['cards'][0]['passed_run'], first)
        final = self.client.post(f"/api/sessions/{self.state['id']}/export-passed", headers=fixtures.HEADERS)
        self.assertEqual(final.status_code, 200)
        with zipfile.ZipFile(io.BytesIO(final.data)) as archive:
            self.assertEqual(len(archive.namelist()), 1)
            self.assertEqual(archive.read(archive.namelist()[0]), first_bytes)
        package = self.client.post(f"/api/sessions/{self.state['id']}/export-experiment", headers=fixtures.HEADERS)
        self.assertEqual(package.status_code, 200, package.json)
        with zipfile.ZipFile(io.BytesIO(package.data)) as archive:
            request_files = [name for name in archive.namelist() if name.endswith('/request.json')]
            saved = [json.loads(archive.read(name)) for name in request_files]
            self.assertEqual({item['output_id'] for item in saved}, {'reference_101'})
            self.assertTrue(all(item['output_slot']['reference_id']=='reference_001' for item in saved))

    def test_same_operation_replays_once_and_changed_request_is_rejected(self):
        operation = uuid4().hex
        with self.fx.with_sdk():
            first = self.generate(operation=operation)
            replay = self.generate(operation=operation, revision=0)
        self.assertEqual(replay.json['run_id'], first.json['run_id'])
        self.assertEqual(len(self.fx.requests), 1)
        changed = self.edit(operation=operation)
        self.assertEqual(changed.status_code, 409)

    def test_failure_preserves_pass_and_uncertainty_blocks_repeat_without_retry(self):
        with self.fx.with_sdk():
            first = self.generate().json['run_id']
        self.review('pass', first)
        def disconnected(request):
            raise httpx.ConnectError('Anonymous disconnected SDK Mock', request=request)
        with self.fx.with_sdk(disconnected):
            failed = self.edit()
        self.assertEqual(failed.status_code, 502)
        card = self.card()
        self.assertEqual(card['passed_run'], first)
        self.assertEqual(card['selected_run'], first)
        self.assertTrue(card['request_uncertain'])
        self.assertEqual(self.edit().status_code, 409)
        self.assertEqual(len(self.fx.requests), 2)
        self.assertTrue((self.run_folder(first)/'image.png').is_file())

    def test_concurrent_double_click_keeps_the_existing_single_image_lock(self):
        entered, release = threading.Event(), threading.Event()
        results = []
        def pending(request):
            entered.set()
            if not release.wait(5):
                raise AssertionError('Offline test did not release model Mock')
            return httpx.Response(200, json={'data':[{'b64_json':base64.b64encode(fixtures.png((1024,1536))).decode()}]})
        with self.fx.with_sdk(pending):
            worker = threading.Thread(target=lambda: results.append(self.generate()))
            worker.start()
            try:
                self.assertTrue(entered.wait(5))
                self.assertEqual(self.generate().status_code, 409)
            finally:
                release.set(); worker.join(5)
        self.assertFalse(worker.is_alive())
        self.assertEqual(results[0].status_code, 200)
        self.assertEqual(len(self.fx.requests), 1)

    def test_tampered_saved_binding_is_rejected_before_execution(self):
        state = self.store.load(self.state['id'])
        state['quick_slots'][0]['reference_id'] = '../outside.png'
        (self.folder/'state.json').write_text(json.dumps(state))
        self.assertEqual(self.client.get(f"/api/sessions/{state['id']}/generation").status_code, 409)
        self.assertFalse((self.folder/'generations').exists())
        self.assertEqual(self.fx.requests, [])


if __name__ == '__main__':
    unittest.main()
