"""E1-04: anonymous temporary inputs, actual SDK serialization, no network."""

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
from image_workflow.planning.conflicts import blockers


class BusinessGuardTests(unittest.TestCase):
    def setUp(self):
        self.fx = generation_fixture.GenerationPageTests()
        self.fx.setUp()
        self.addCleanup(self.fx.doCleanups)
        self.client, self.store = self.fx.client, self.fx.store
        self.enterContext(patch('socket.socket.connect', side_effect=AssertionError('Offline only')))
        self.planner = planning_fixture.PreparePlanTests()
        self.planner.requests = []

    def saved(self, response):
        self.assertEqual(response.status_code, 200, response.json)
        return response.json['state']

    def create(self, mode='quick_a', source='product_002', declared=True):
        rows = [dict(id='reference_101', type='dimensions', enabled=True, reference_id='reference_001',
                     requirements='', dimension_source_product_id=source, dimension_source_confirmed=declared),
                dict(id='reference_102', type='scene', enabled=True, reference_id='reference_002', requirements='')]
        form = dict(title='Anonymous E1-04', mode='product_pack', listing='接口为 USB-C；支持无线功能。',
                    description='运营提供的商品宣称，非独立认证。', requirements='日语；不猜测尺寸。',
                    product=[(io.BytesIO(generation_fixture.png((24+i, 32))), f'own-{i}.png') for i in range(3)],
                    reference=[(io.BytesIO(generation_fixture.png((32, 40+i))), f'ref-{i}.png') for i in range(2)])
        if mode == 'listing':
            form['listing_slots'] = json.dumps(rows)
        else:
            form.update(mode='quick_redesign', quick_business_version='v1', quick_scenario=mode, quick_slots=json.dumps(rows))
        return self.client.post('/api/sessions', headers=generation_fixture.HEADERS, data=form)

    def files(self, state):
        return {str(p.relative_to(self.store.folder(state['id']))): p.read_bytes()
                for p in self.store.folder(state['id']).rglob('*') if p.is_file()}

    def action(self, state, kind, target=None, **extra):
        return self.client.post(f"/api/sessions/{state['id']}/action", headers=generation_fixture.HEADERS,
            json={**dict(action=kind, target=target, revision=state['revision']), **extra})

    def report(self, kind='VISIBLE_CONTRADICTION', target='reference_002'):
        return dict(conflict_id='connector', affected_claim='接口为 USB-C',
            text_evidence=dict(source='listing', quote='接口为 USB-C'),
            visual_evidence=dict(product_image_ids=['product_001'], observation='匿名 Mock 报告：可见接口与文字不同，未经真实识别验证'),
            issue_type=kind, affected_image_ids=[target])

    def plan(self, state, reports=None, action='understand', **extra):
        def handler(body, result):
            result['fact_issues'] = [] if reports is None else reports
            return httpx.Response(200, json=dict(id='resp_mock_guard', object='response', created_at=1,
                model=body['model'], status='completed', output=[dict(type='message', id='msg_mock', role='assistant',
                status='completed', content=[dict(type='output_text', text=json.dumps(result), annotations=[])])]))
        with self.planner.with_ai(handler):
            return self.action(state, action, **extra)

    def card(self, state, target):
        return next(c for c in self.client.get(f"/api/sessions/{state['id']}/generation").json['cards'] if c['id'] == target)

    def generate(self, state, target, editing=False, operation=None, batch=False):
        card = self.card(state, target)
        return self.client.post(f"/api/sessions/{state['id']}/{'revise' if editing else 'generate'}/{target}",
            headers=generation_fixture.HEADERS, json=dict(confirmed_revision=card['generation_revision'],
            card_revision=card['card_revision'], operation_id=operation or uuid4().hex, batch_only=batch,
            **(dict(parent_run_id=card['selected_run'] or '20261028T000000Z-' + 'a' * 32, feedback='仅调整背景') if editing else {})))

    def test_dimension_role_foreign_reference_and_declaration_validate_before_task_write(self):
        before = sorted(p.name for p in (self.store.root / 'sessions').iterdir())
        for source, declared in [('reference_001', True), ('foreign/product_002', True), ('product_999', True),
                                 (None, True), ('product_002', 'true')]:
            self.assertEqual(self.create(source=source, declared=declared).status_code, 400)
        self.assertEqual(before, sorted(p.name for p in (self.store.root / 'sessions').iterdir()))

    def test_missing_declaration_blocks_generate_edit_batch_and_no_run(self):
        for mode in ('quick_a', 'quick_b', 'listing'):
            for source, declared in [(None, False), ('product_002', False)]:
                state = self.saved(self.create(mode, source, declared))
                if mode == 'listing':
                    state = self.saved(self.plan(state))
                    state = self.saved(self.action(state, 'confirm', 'reference_001'))
                target = 'reference_001' if mode == 'listing' else 'reference_101'
                before = self.files(state)
                card = self.card(state, target)
                self.assertFalse(card['generation_allowed']); self.assertFalse(card['batch_eligible'])
                for editing in (False, True):
                    response = self.generate(state, target, editing)
                    self.assertEqual(response.status_code, 409, response.json)
                    self.assertIn('尺寸', response.json['error'])
                self.assertEqual(self.generate(state, target, batch=True).status_code, 409)
                self.assertEqual(self.files(state), before)
        self.assertEqual(self.fx.requests, [])

    def test_valid_dimensions_all_modes_actual_request_edit_parent_dedup_and_missing_file(self):
        for mode in ('quick_a', 'quick_b', 'listing'):
            state = self.saved(self.create(mode))
            if mode == 'listing':
                state = self.saved(self.plan(state)); state = self.saved(self.action(state, 'confirm', 'reference_001'))
            target = 'reference_001' if mode == 'listing' else 'reference_101'
            operation = uuid4().hex
            with self.fx.with_sdk():
                generated = self.generate(state, target, operation=operation)
                self.assertEqual(generated.status_code, 200, generated.json)
                again = self.generate(state, target, operation=operation)
                self.assertEqual(again.json['run_id'], generated.json['run_id'])
                first = self.card(state, target)
                accepted = self.client.post(f"/api/sessions/{state['id']}/review/{target}", headers=generation_fixture.HEADERS,
                    json=dict(action='pass', run_id=generated.json['run_id'], confirmed_revision=first['generation_revision'], card_revision=first['card_revision']))
                self.assertEqual(accepted.status_code, 200, accepted.json)
                revised = self.generate(state, target, editing=True)
                self.assertEqual(revised.status_code, 200, revised.json)
            service = self.fx.app.extensions['generation_service']
            card = self.card(state, target)
            folder = service.run_folder(state['id'], card['generation_revision'], target, revised.json['run_id'])
            request = json.loads((folder / 'request.json').read_text())
            context = json.loads((folder / 'plan.json').read_text())
            self.assertEqual(card['passed_run'], generated.json['run_id'])
            wire = self.fx.requests[-1]
            parts = BytesParser().parsebytes(('Content-Type: ' + wire.headers['content-type'] + '\r\n\r\n').encode() + wire.read()).get_payload()
            wire_prompt = next(part.get_payload(decode=True).decode() for part in parts if part.get_param('name', header='content-disposition') == 'prompt')
            self.assertEqual(wire_prompt, request['prompt'])
            wire_images = [part.get_payload(decode=True) for part in parts if part.get_filename()]
            self.assertEqual(len(wire_images), 5)
            self.assertEqual(wire_images[1:4], [self.store.read_input(state['id'], f'inputs/product_{i:03}.png') for i in range(1, 4)])
            self.assertEqual(wire_images[-1], self.store.read_input(state['id'], 'inputs/reference_001.png'))
            self.assertEqual(context['output_slot']['dimension_source_product_id'], 'product_002')
            self.assertEqual(context['parent_image']['run_id'], generated.json['run_id'])
            self.assertIn('尺寸专项依据：product_002', request['prompt'])
            self.assertEqual([i['id'] for i in request['image_order']],
                ['current_image', 'product_001', 'product_002', 'product_003', 'reference_001'])
            self.assertEqual([i['role'] for i in request['image_order']][1:4], ['product'] * 3)
            run = json.loads((folder / 'run.json').read_text())
            self.assertEqual(run['max_retries'], 0)
            # Delete only an anonymous temporary fixture input, not real Evidence.
            self.store.folder(state['id']).joinpath('inputs/product_002.png').unlink()
            self.assertFalse(self.card(state, target)['generation_allowed'])
            self.assertEqual(self.generate(state, target, editing=True).status_code, 409)
        self.assertEqual(len(self.fx.requests), 6)

    def test_dimension_save_as_remaps_owned_product_and_preserves_old_snapshots(self):
        state = self.saved(self.create())
        before = self.files(state)
        rows = copy.deepcopy(state['quick_slots']); rows[0]['dimension_source_product_id'] = 'product_001'
        clone = self.saved(self.client.post('/api/sessions', headers=generation_fixture.HEADERS, data=dict(
            title='New copy', mode=state['mode'], from_session=state['id'], quick_scenario=state['quick_scenario'],
            quick_business_version='v1', quick_slots=json.dumps(rows), **state['inputs'],
            keep_images=json.dumps(['product_002', 'product_003', 'reference_001', 'reference_002']))))
        self.assertEqual(clone['quick_slots'][0]['dimension_source_product_id'], 'product_001')
        self.assertEqual(clone['images'][0]['sha256'], state['images'][1]['sha256'])
        self.assertEqual(self.files(state), before)
        self.assertTrue(self.card(clone, 'reference_101')['generation_allowed'])

    def test_report_blocks_only_affected_plan_confirmation_and_direct_generation(self):
        state = self.saved(self.plan(self.saved(self.create('listing')), [self.report()]))
        issue = state['fact_issues'][0]
        self.assertEqual(issue['resolution_status'], 'UNRESOLVED')
        self.assertEqual(issue['text_evidence']['quote'], '接口为 USB-C')
        self.assertEqual(self.action(state, 'confirm', 'reference_002').status_code, 409)
        self.assertEqual(self.generate(state, 'reference_002').status_code, 409)
        state = self.saved(self.action(state, 'confirm', 'reference_001'))
        self.assertTrue(state['plan_status']['reference_001']['confirmed'])
        before_calls = len(self.planner.requests)
        state = self.saved(self.action(state, 'resolve_conflict', conflict_id=issue['conflict_id'], decision='RETAIN', note='运营按实物资料决定继续使用，非独立认证'))
        self.assertEqual(len(self.planner.requests), before_calls)
        self.assertFalse(state['plan_status']['reference_002']['confirmed'])
        state = self.saved(self.action(state, 'confirm', 'reference_002'))
        self.assertTrue(state['plan_status']['reference_001']['confirmed'])
        with self.fx.with_sdk():
            response = self.generate(state, 'reference_002')
        self.assertEqual(response.status_code, 200, response.json)
        service = self.fx.app.extensions['generation_service']
        folder = service.run_folder(state['id'], self.card(state, 'reference_002')['generation_revision'], 'reference_002', response.json['run_id'])
        context = json.loads((folder / 'plan.json').read_text())
        self.assertEqual(context['operator_fact_review'][0]['operator_resolution']['decision'], 'RETAIN')
        self.assertEqual(context['operator_fact_review'][0]['resolution_status'], 'RESOLVED')

    def test_new_report_blocks_an_unchanged_previously_confirmed_plan_and_cached_state(self):
        state = self.saved(self.plan(self.saved(self.create('listing'))))
        state = self.saved(self.action(state, 'confirm', 'reference_002'))
        cached = self.store.image_state(self.store.load(state['id']), 'reference_002')
        confirmation = copy.deepcopy(state['plan_status']['reference_002']['confirmation'])
        plan = copy.deepcopy(state['plans']['reference_002'])
        # A report obtained while changing another plan must still invalidate
        # the affected card's old confirmation, even though its plan is unchanged.
        state = self.saved(self.plan(state, [self.report()], action='plan', target='reference_001', feedback='仅修改第一张计划'))
        self.assertEqual(state['plans']['reference_002'], plan)
        self.assertEqual(state['plan_status']['reference_002']['confirmation'], confirmation)
        self.assertFalse(state['plan_status']['reference_002']['confirmed'])
        self.assertEqual(self.action(state, 'confirm', 'reference_002').status_code, 409)
        self.assertEqual(self.generate(state, 'reference_002').status_code, 409)
        from image_workflow import Problem
        with self.assertRaises(Problem):
            self.fx.app.extensions['generation_service'].generate(cached, 'reference_002')
        self.assertEqual(self.fx.requests, [])

    def test_unseen_feature_is_not_visible_contradiction_and_bad_source_is_not_applied(self):
        state = self.saved(self.create('listing'))
        bad = self.report(); bad['text_evidence']['quote'] = '不存在于商品文字中的句子'
        before = self.store.load(state['id'])
        failed = self.plan(state, [bad]); self.assertEqual(failed.status_code, 502)
        self.assertEqual(self.store.load(state['id']), before)
        state = self.saved(self.plan(state, [self.report('INSUFFICIENT_EVIDENCE')]))
        state = self.saved(self.action(state, 'confirm', 'reference_002'))
        self.assertTrue(state['plan_status']['reference_002']['confirmed'])
        prompt = self.planner.requests[-1]['input'][0]['content'][0]['text']
        self.assertIn('未拍到', prompt); self.assertIn('INSUFFICIENT_EVIDENCE', prompt)

    def test_correct_or_exclude_revises_plan_requires_reconfirmation_and_expires_on_replan(self):
        for decision in ('CORRECT', 'EXCLUDE'):
            state = self.saved(self.plan(self.saved(self.create('listing')), [self.report()]))
            issue = state['fact_issues'][0]
            plans = {'reference_002': {key: '修订计划：不使用争议接口宣称' for key in generation_fixture.web.PLAN_FIELDS}}
            stale = self.action(state, 'resolve_conflict', revision=0, conflict_id=issue['conflict_id'], decision=decision, note='说明')
            self.assertEqual(stale.status_code, 409)
            self.assertEqual(self.action(state, 'resolve_conflict', conflict_id=issue['conflict_id'], decision=decision, note='修正', plans={}).status_code, 400)
            state = self.saved(self.action(state, 'resolve_conflict', conflict_id=issue['conflict_id'], decision=decision, note='不再使用该宣称；保留原始来源作为历史', plans=plans))
            self.assertEqual(state['plans']['reference_002'], plans['reference_002'])
            self.assertEqual(state['fact_issues'][0]['operator_resolution']['revision'], state['revision'])
            state = self.saved(self.action(state, 'confirm', 'reference_002'))
            with self.fx.with_sdk():
                self.assertEqual(self.generate(state, 'reference_002').status_code, 200)
            state = self.saved(self.plan(state, action='replan'))
            self.assertEqual(state['fact_issues'][0]['resolution_status'], 'STALE')
            self.assertTrue(blockers(state, 'reference_002'))
            self.assertEqual(self.action(state, 'confirm', 'reference_002').status_code, 409)
            self.assertEqual(self.generate(state, 'reference_002').status_code, 409)

    def test_changed_input_copy_does_not_inherit_fact_resolution_or_plan_confirmation(self):
        state = self.saved(self.plan(self.saved(self.create('listing')), [self.report()]))
        state = self.saved(self.action(state, 'resolve_conflict', conflict_id=state['fact_issues'][0]['conflict_id'], decision='RETAIN', note='当前资料的人工处理'))
        state = self.saved(self.action(state, 'confirm', 'reference_002'))
        before = self.files(state)
        clone = self.saved(self.client.post('/api/sessions', headers=generation_fixture.HEADERS, data=dict(
            title='Changed text copy', mode='product_pack', from_session=state['id'],
            keep_images=json.dumps([image['id'] for image in state['images']]),
            listing='新的商品宣称；旧争议决定不可沿用', description=state['inputs']['description'], requirements=state['inputs']['requirements'],
            listing_slots=json.dumps(state['listing_slots']))))
        self.assertNotIn('fact_issues', clone)
        self.assertFalse(clone['confirmed']); self.assertIsNone(clone['product'])
        self.assertEqual(self.action(clone, 'confirm', 'reference_002').status_code, 400)
        self.assertEqual(self.generate(clone, 'reference_002').status_code, 409)
        self.assertEqual(self.files(state), before)

    def test_changed_dimension_bytes_or_role_never_reach_sdk(self):
        state = self.saved(self.create())
        folder = self.store.folder(state['id'])
        (folder / 'inputs/product_002.png').write_bytes(generation_fixture.png((99, 99)))
        with self.fx.with_sdk():
            failed = self.generate(state, 'reference_101')
        self.assertEqual(failed.status_code, 400, failed.json)
        self.assertEqual(self.fx.requests, [])
        record = next(folder.glob('generations/**/runs/*/run.json'))
        self.assertFalse(json.loads(record.read_text())['api_call_attempted'])
        # Corrupt only an anonymous fixture's role to exercise persisted ownership checks.
        saved = json.loads((folder / 'state.json').read_text()); saved['images'][1]['role'] = 'reference'
        (folder / 'state.json').write_text(json.dumps(saved))
        self.assertEqual(self.client.get('/api/sessions/' + state['id']).status_code, 409)
        self.assertEqual(self.fx.requests, [])

    def test_legacy_listing_existing_versions_pass_and_zip_remain_usable(self):
        state = self.fx.confirmed(3, classified=False)
        historical = copy.deepcopy(state)
        historical['listing_slots'] = [dict(id='reference_101', type='selling_point', enabled=True, reference_id='reference_001')]
        service = self.fx.app.extensions['generation_service']
        # Create an anonymous historical-result fixture via SDK Mock. The Task
        # snapshots stay unclassified; no real or archived record is rewritten.
        with self.fx.with_sdk():
            record = service._generate(historical, 'reference_001')
        self.assertEqual(record['status'], 'SUCCEEDED')
        before_snapshots = {name: data for name, data in self.files(state).items() if name.startswith('versions/')}
        card = self.card(state, 'reference_001')
        self.assertFalse(card['generation_allowed']); self.assertTrue(card['review_allowed'])
        self.assertFalse(card['historical_generation'])
        accepted = self.client.post(f"/api/sessions/{state['id']}/review/reference_001", headers=generation_fixture.HEADERS,
            json=dict(action='pass', run_id=record['run_id'], confirmed_revision=state['revision'], card_revision=card['card_revision']))
        self.assertEqual(accepted.status_code, 200, accepted.json)
        downloaded = self.client.post(f"/api/sessions/{state['id']}/export-passed", headers=generation_fixture.HEADERS)
        self.assertEqual(downloaded.status_code, 200)
        downloaded.close()
        self.assertEqual(self.generate(state, 'reference_001').status_code, 409)
        self.assertEqual(before_snapshots, {name: data for name, data in self.files(state).items() if name.startswith('versions/')})

    def test_operator_resolution_is_free_even_when_live_debug_paid_gate_is_locked(self):
        state = self.saved(self.plan(self.saved(self.create('listing')), [self.report()]))
        debug = generation_fixture.web.create_local_debug_app(self.fx.runtime, [state['id']],
            execution_mode='LIVE DEBUG', allow_paid_actions=False).test_client()
        with patch.dict('os.environ', {'OPENAI_API_KEY': ''}):
            response = debug.post(f"/api/sessions/{state['id']}/action", headers=generation_fixture.HEADERS,
                json=dict(action='resolve_conflict', revision=state['revision'], conflict_id=state['fact_issues'][0]['conflict_id'],
                          decision='RETAIN', note='运营处理；不调用模型'))
        self.assertEqual(response.status_code, 200, response.json)
        self.assertFalse(response.json['state']['plan_status']['reference_002']['confirmed'])
        self.assertEqual(len(self.planner.requests), 1)

    def test_legacy_listing_is_readable_but_unclassified_new_execution_is_blocked_without_rewrite(self):
        state = self.fx.confirmed(3, classified=False)
        before = self.files(state)
        self.assertEqual(self.client.get('/api/sessions/' + state['id']).status_code, 200)
        self.assertFalse(self.card(state, 'reference_001')['generation_allowed'])
        self.assertEqual(self.generate(state, 'reference_001').status_code, 409)
        self.assertEqual(self.files(state), before)
        self.assertNotIn('listing_slots', self.store.load(state['id']))

    def test_legacy_listing_size_map_can_be_replaced_by_explicit_classified_copy(self):
        state = self.fx.confirmed(3, classified=False)
        state['image_sizes'] = {'reference_001': '1536x1024', 'reference_002': '1024x1024'}
        self.store.save(state, {'action': 'anonymous_size_fixture', 'target': None, 'feedback': ''})
        before = self.files(state)
        form = dict(title='Explicitly classified copy', mode='product_pack', from_session=state['id'],
                    keep_images=json.dumps([image['id'] for image in state['images']]), **state['inputs'])
        # Omitting both size representations remains forbidden for an ordinary legacy copy.
        self.assertEqual(self.client.post('/api/sessions', headers=generation_fixture.HEADERS, data=form).status_code, 400)
        rows = [dict(id=f'reference_{101+i}', type='selling_point', enabled=True,
                     reference_id=f'reference_{i+1:03}', requirements='',
                     output_size=state['image_sizes'].get(f'reference_{i+1:03}', '1024x1536')) for i in range(3)]
        clone = self.saved(self.client.post('/api/sessions', headers=generation_fixture.HEADERS,
                                           data={**form, 'listing_slots': json.dumps(rows)}))
        self.assertNotEqual(clone['id'], state['id'])
        self.assertEqual(clone['listing_slots'], rows)
        self.assertNotIn('image_sizes', clone)
        self.assertEqual(clone['plans'], {}); self.assertFalse(clone['confirmed'])
        self.assertEqual([image['sha256'] for image in clone['images']], [image['sha256'] for image in state['images']])
        self.assertEqual(self.files(state), before)


if __name__ == '__main__':
    unittest.main()
