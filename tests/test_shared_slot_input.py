"""E1-01 inputs only: anonymous temporary Tasks, official SDK + MockTransport."""

import base64
import copy
from email.parser import BytesParser
import io
import json
import unittest
from unittest.mock import patch
from uuid import uuid4

import httpx
import test_generate_plan_image as generation_fixture
import test_prepare_plan as planning_fixture
from image_workflow.generation import quick_v1
from image_workflow.planning.request import reference_ids


def configuration():
    # Form row IDs intentionally differ from Listing reference/plan IDs.
    return [
        dict(id='reference_101', type='main', enabled=True, reference_id='reference_002',
             requirements='主图补充要求', output_size='1024x1024'),
        dict(id='reference_102', type='dimensions', enabled=True, reference_id='reference_001',
             requirements='仅采用商品尺寸素材的标注', output_size='1536x1024'),
        dict(id='reference_103', type='scene', enabled=False, reference_id='reference_003',
             requirements='暂不制作', output_size='1024x1536'),
    ]


class SharedSlotInputTests(unittest.TestCase):
    def setUp(self):
        self.fx = generation_fixture.GenerationPageTests()
        self.fx.setUp()
        self.addCleanup(self.fx.doCleanups)
        self.client, self.store = self.fx.client, self.fx.store
        self.enterContext(patch('socket.socket.connect', side_effect=AssertionError('Offline only')))
        self.enterContext(patch.object(generation_fixture.web, 'OpenAI', side_effect=AssertionError('No real Planning')))

    def create(self, scenario=None, slots=None, **extra):
        rows = configuration() if slots is None else slots
        form = dict(title='Anonymous E1-01', mode='product_pack', listing='运营提供 Listing，尚未核实',
                    description='商品描述', requirements='共同要求',
                    product=[(io.BytesIO(generation_fixture.png((24+i, 32))), f'product-{i}.png') for i in range(3)],
                    reference=[(io.BytesIO(generation_fixture.png((32, 40+i))), f'ref-{i}.png') for i in range(3)])
        if scenario:
            form.update(mode='quick_redesign', quick_business_version='v1', quick_scenario=scenario,
                        quick_slots=json.dumps([{k: v for k, v in slot.items() if k != 'output_size'} for slot in rows]))
        else:
            form['listing_slots'] = json.dumps(rows)
        return self.client.post('/api/sessions', headers=generation_fixture.HEADERS, data={**form, **extra})

    def saved(self, response):
        self.assertEqual(response.status_code, 200, response.json)
        return response.json['state']

    def files(self, state):
        return {str(p.relative_to(self.store.folder(state['id']))): p.read_bytes()
                for p in self.store.folder(state['id']).rglob('*') if p.is_file()}

    def clone(self, state, **extra):
        form = dict(title='Anonymous separate copy', mode=state['mode'], from_session=state['id'],
                    keep_images=json.dumps([image['id'] for image in state['images']]), **state['inputs'])
        for key in ('quick_scenario', 'quick_business_version', 'quick_slots', 'listing_slots'):
            if key in state:
                form[key] = json.dumps(state[key]) if key.endswith('slots') else state[key]
        return self.client.post('/api/sessions', headers=generation_fixture.HEADERS, data={**form, **extra})

    def test_three_entries_and_explicit_quick_scenarios_restore_and_clone(self):
        page = self.client.get('/workspace/new').get_data(as_text=True)
        for label in ('Quick-A｜同款快速改版', 'Quick-B｜换主体快速改版', 'Listing｜商品资料制图'):
            self.assertIn(label, page)
        for scenario in quick_v1.SCENARIOS:
            with self.subTest(scenario=scenario):
                state = self.saved(self.create(scenario))
                before = self.files(state)
                restored = self.client.get('/api/sessions/' + state['id']).json['state']
                self.assertEqual(restored['mode'], 'quick_redesign')
                self.assertEqual(restored['quick_scenario'], scenario)
                self.assertEqual(restored['quick_slots'], state['quick_slots'])
                self.assertEqual([i['role'] for i in restored['images']], ['product'] * 3 + ['reference'] * 3)
                clone = self.saved(self.clone(state))
                self.assertNotEqual(clone['id'], state['id'])
                self.assertEqual(clone['quick_scenario'], scenario)
                self.assertEqual(clone['quick_slots'], state['quick_slots'])
                self.assertEqual(self.files(state), before)

    def test_new_scenario_dimensions_remain_blocked_without_creating_runs(self):
        for scenario in quick_v1.SCENARIOS:
            state = self.saved(self.create(scenario))
            before = self.files(state)
            cards = self.client.get(f"/api/sessions/{state['id']}/generation").json['cards']
            self.assertTrue(cards)
            dimensions = next(card for card in cards if card['id'] == 'reference_102')
            self.assertFalse(dimensions['generation_allowed'])
            self.assertFalse(dimensions['batch_eligible'])
            self.assertIn('E1-04', dimensions['generation_block_reason'])
            self.assertTrue(all(card['generation_allowed'] for card in cards if card['id'] != 'reference_102'))
            with patch.object(generation_fixture.generation, 'make_client', side_effect=AssertionError('No SDK')):
                for action in ('generate', 'revise'):
                    result = self.client.post(f"/api/sessions/{state['id']}/{action}/reference_102",
                        headers=generation_fixture.HEADERS, json=dict(confirmed_revision=1, card_revision=0,
                            operation_id=uuid4().hex, parent_run_id='20261028T000000Z-' + 'a' * 32, feedback='只改背景'))
                    self.assertEqual(result.status_code, 409, result.json)
                    self.assertIn('ENGINEERING PARTIAL', result.json['error'])
                    self.assertIn('E1-04', result.json['error'])
            self.assertEqual(self.files(state), before)

    def test_historical_quick_and_listing_never_gain_inferred_classification(self):
        for mode, version in [('quick_redesign', None), ('quick_redesign', 'v1'), ('product_pack', None)]:
            kwargs = {} if version is None else dict(quick_business_version=version,
                quick_slots=[{k: v for k, v in slot.items() if k != 'output_size'} for slot in configuration()])
            state = self.store.create(dict(listing='', description='', requirements='旧策略'),
                [('product', 'own.png', generation_fixture.png())] +
                [('reference', f'{i}.png', generation_fixture.png()) for i in range(3)], '历史匿名任务', mode=mode, **kwargs)
            before = self.files(state)
            for restored in (self.store.load(state['id']), self.client.get('/api/sessions/' + state['id']).json['state'],
                             self.saved(self.clone(state))):
                self.assertNotIn('quick_scenario', restored)
                self.assertNotIn('listing_slots', restored)
            if mode == 'quick_redesign':
                cards = self.client.get(f"/api/sessions/{state['id']}/generation").json['cards']
                self.assertTrue(all(card['generation_allowed'] for card in cards))
            self.assertEqual(self.files(state), before)

    def test_listing_restore_clone_and_reference_remap_keep_source_unchanged(self):
        state = self.saved(self.create())
        before = self.files(state)
        self.assertEqual(reference_ids(state), ['reference_002', 'reference_001'])
        self.assertEqual(self.store.load(state['id'])['listing_slots'], configuration())
        rows = copy.deepcopy(state['listing_slots'][:1])
        rows[0]['reference_id'] = 'reference_001'
        clone = self.saved(self.clone(state, keep_images=json.dumps(['product_001', 'reference_002']),
                                       listing_slots=json.dumps(rows)))
        self.assertEqual(clone['listing_slots'][0]['id'], 'reference_101')
        self.assertEqual(clone['listing_slots'][0]['reference_id'], 'reference_001')
        old = next(i for i in state['images'] if i['id'] == 'reference_002')
        new = next(i for i in clone['images'] if i['id'] == 'reference_001')
        self.assertEqual(old['sha256'], new['sha256'])
        self.assertEqual(clone['inputs'], state['inputs'])
        self.assertEqual(clone['plans'], {})
        self.assertFalse(clone['confirmed'])
        self.assertEqual(self.files(state), before)

    def test_listing_classification_enters_planning_without_replacing_plan_identity(self):
        state = self.saved(self.create())
        helper = planning_fixture.PreparePlanTests()
        helper.requests = []
        def action(current, kind, target=None, **extra):
            return self.client.post(f"/api/sessions/{current['id']}/action", headers=generation_fixture.HEADERS,
                json=dict(action=kind, revision=current['revision'], target=target, feedback='', **extra))
        # Generation is still blocked before real Planning + human confirmation.
        self.assertEqual(self.client.post(f"/api/sessions/{state['id']}/generate/reference_002",
            headers=generation_fixture.HEADERS, json={'confirmed_revision': 1}).status_code, 409)
        with helper.with_ai():
            state = self.saved(action(state, 'understand'))
        content = helper.requests[0]['input'][0]['content']
        context = json.loads(content[0]['text'])
        self.assertEqual(context['output_slot_inputs'], {row['reference_id']: row for row in configuration() if row['enabled']})
        self.assertEqual(context['original_inputs'], state['inputs'])
        self.assertEqual(context['required_reference_ids'], ['reference_002', 'reference_001'])
        self.assertEqual(len([item for item in content if item['type'] == 'input_image']), 5)
        self.assertFalse(any(item.get('text', '').startswith('reference_003：') for item in content))
        self.assertEqual(set(state['plans']), {'reference_001', 'reference_002'})
        self.assertNotIn('reference_101', state['plans'])
        self.assertFalse(state['plan_status']['reference_002']['confirmed'])
        state = self.saved(action(state, 'confirm', 'reference_002',
            plan_version=state['plan_status']['reference_002']['plan_version']))
        confirmed = self.store.image_state(self.store.load(state['id']), 'reference_002')
        snapshot = self.store.read_snapshot(state['id'], confirmed['revision'])
        before = self.files(state)
        def response(request):
            message = BytesParser().parsebytes(('Content-Type: ' + request.headers['content-type'] + '\r\n\r\n').encode() + request.read())
            parameters = {part.get_param('name', header='content-disposition'): part.get_payload(decode=True)
                          for part in message.get_payload() if not part.get_filename()}
            self.assertEqual(parameters['size'], b'1024x1024')
            return httpx.Response(200, json={'data': [{'b64_json': base64.b64encode(generation_fixture.png((1024, 1024))).decode()}]})
        with self.fx.with_sdk(response):
            generated = self.client.post(f"/api/sessions/{state['id']}/generate/reference_002",
                headers=generation_fixture.HEADERS, json={'confirmed_revision': confirmed['revision'], 'operation_id': uuid4().hex})
        self.assertEqual(generated.status_code, 200, generated.json)
        record = generated.json
        self.assertEqual(record['status'], 'SUCCEEDED')
        folder = self.fx.app.extensions['generation_service'].run_folder(state['id'], confirmed['revision'], 'reference_002', record['run_id'])
        request = json.loads((folder / 'request.json').read_text())
        self.assertEqual(request['size'], '1024x1024')
        order = request['image_order']
        self.assertEqual([i['id'] for i in order], ['product_001', 'product_002', 'product_003', 'reference_002'])
        self.assertEqual(self.store.read_snapshot(state['id'], confirmed['revision']), snapshot)
        for path, data in before.items():
            self.assertEqual((self.store.folder(state['id']) / path).read_bytes(), data)
        cards = self.client.get(f"/api/sessions/{state['id']}/generation").json['cards']
        self.assertEqual([c['id'] for c in cards], ['reference_002', 'reference_001'])
        self.assertEqual([c['output_size'] for c in cards], ['1024x1024', '1536x1024'])

    def test_targeted_listing_planning_receives_only_its_bound_row_and_reference(self):
        from image_workflow.planning.request import build_planning_request
        state = self.saved(self.create())
        blobs = {image['file']: self.store.read_input(state['id'], image['file']) for image in state['images']}
        for action in ('reference', 'plan'):
            args, order = build_planning_request(state, action, 'reference_001', '仅修改本张', 'offline-model', blobs,
                                                reasoning_model='offline-reasoning')
            context = json.loads(args['input'][0]['content'][0]['text'])
            self.assertEqual(context['output_slot_inputs'], {'reference_001': configuration()[1]})
            self.assertEqual([i['id'] for i in order], ['product_001', 'product_002', 'product_003', 'reference_001'])
        args, order = build_planning_request(state, 'product', None, '修正商品资料', 'offline-model', blobs,
                                            reasoning_model='offline-reasoning')
        self.assertNotIn('output_slot_inputs', json.loads(args['input'][0]['content'][0]['text']))
        self.assertEqual([i['role'] for i in order], ['product'] * 3)

    def test_invalid_mode_role_foreign_binding_and_sizes_fail_before_any_task_write(self):
        before = set(self.store.root.rglob('*'))
        for reference in ('product_001', 'reference_999', '../other/reference_001', 'f' * 32 + ':reference_001'):
            rows = configuration()
            rows[0]['reference_id'] = reference
            self.assertEqual(self.create(slots=rows).status_code, 400)
        for field, value in [('output_size', '100x100'), ('enabled', 'true'), ('path', '/etc/passwd')]:
            rows = configuration()
            rows[0][field] = value
            self.assertEqual(self.create(slots=rows).status_code, 400)
        self.assertEqual(self.create(quick_scenario='quick_a').status_code, 400)
        self.assertEqual(self.create('quick_a', quick_business_version='legacy').status_code, 400)
        self.assertEqual(self.create('unknown').status_code, 400)
        self.assertEqual(self.create(image_sizes='{"reference_002":"1024x1024"}').status_code, 400)
        self.assertEqual(self.create(listing_slots='null').status_code, 400)
        self.assertEqual(set(self.store.root.rglob('*')), before)

    def test_listing_and_quick_keep_singleton_caps_and_unique_binding_checks(self):
        for scenario in (None, 'quick_a'):
            for kind, maximum in ((kind, data[0]) for kind, data in quick_v1.SLOT_TYPES.items()):
                if maximum is None:
                    continue  # Replaced by dynamic-N acceptance tests, not a new cap.
                rows = [dict(id=f'reference_{100+i}', type=kind, enabled=False, reference_id=None,
                             output_size='1024x1536') for i in range(maximum+1)]
                self.assertEqual(self.create(scenario, slots=rows).status_code, 400)
            rows = configuration()
            rows[1]['reference_id'] = rows[0]['reference_id']
            self.assertEqual(self.create(scenario, slots=rows).status_code, 400)

    def test_clone_cannot_drop_or_change_explicit_scenario_or_listing_metadata(self):
        state = self.saved(self.create('quick_b'))
        self.assertEqual(self.clone(state, quick_scenario='quick_a').status_code, 400)
        self.assertEqual(self.clone(state, quick_scenario='').status_code, 400)
        state = self.saved(self.create())
        self.assertEqual(self.client.post('/api/sessions', headers=generation_fixture.HEADERS, data=dict(
            title='missing metadata', mode='product_pack', from_session=state['id'],
            keep_images=json.dumps([i['id'] for i in state['images']]))).status_code, 400)

    def test_corrupt_new_metadata_is_rejected_on_read_without_repair(self):
        for scenario in (None, 'quick_a'):
            state = self.saved(self.create(scenario))
            path = self.store.folder(state['id']) / 'state.json'
            raw = json.loads(path.read_text())
            if scenario:
                raw['quick_scenario'] = 'auto-inferred'
            else:
                raw['listing_slots'][0]['reference_id'] = 'product_001'
            path.write_text(json.dumps(raw))
            before = path.read_bytes()
            self.assertEqual(self.client.get('/api/sessions/' + state['id']).status_code, 409)
            self.assertEqual(path.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
