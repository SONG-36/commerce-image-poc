"""V1 operator actions with anonymous temporary files and real SDK serialization."""

import copy
from email.parser import BytesParser
import io
import json
from unittest.mock import patch
import unittest
from uuid import uuid4
import zipfile

import app
import test_business_guards as fixtures
from image_workflow.planning.conflicts import blockers, issue_views


HEADERS = {'X-Local-Action': 'prepare-plan'}


class UsabilityTests(unittest.TestCase):
    def setUp(self):
        self.fx = fixtures.BusinessGuardTests()
        self.fx.setUp()
        self.addCleanup(self.fx.doCleanups)
        self.client, self.store = self.fx.client, self.fx.store

    def listing(self, reports=None):
        state = self.fx.saved(self.fx.create('listing'))
        return self.fx.saved(self.fx.plan(state, reports))

    def manual(self, state, target='reference_002', **extra):
        plan = {**state['plans'][target], 'selling_points': '0° / 15° / 25° / 40° / ミスト；泡沫附件独立'}
        return self.fx.action(state, 'manual_plan', target, plan=plan,
                              plan_version=state['plan_versions'][target], **extra)

    def quality(self, state, quality='medium', overrides=None, **extra):
        return self.client.post(f"/api/sessions/{state['id']}/action", headers=HEADERS,
            json={**dict(action='set_quality', revision=state['revision'], quality_revision=state.get('quality_revision', 0),
                         generation_quality=quality, image_qualities=overrides or {}), **extra})

    def generate(self, state, target, edit=False, operation=None, **extra):
        card = self.fx.card(state, target)
        body = dict(confirmed_revision=card['generation_revision'], card_revision=card['card_revision'],
                    operation_id=operation or uuid4().hex, quality=card.get('quality', 'low'),
                    quality_revision=card.get('quality_revision', 0))
        if edit:
            body.update(parent_run_id=card['selected_run'], feedback='保留主体，调整背景')
        return self.client.post(f"/api/sessions/{state['id']}/{'revise' if edit else 'generate'}/{target}",
                                headers=HEADERS, json={**body, **extra})

    def review(self, state, kind, target='reference_002', **extra):
        card = self.fx.card(state, target)
        return self.client.post(f"/api/sessions/{state['id']}/review/{target}", headers=HEADERS,
            json={**dict(action=kind, confirmed_revision=card['confirmed_revision'],
                         card_revision=card['card_revision'], run_id=card['selected_run']), **extra})

    def test_manual_edits_one_plan_without_planning_and_preserves_original_call(self):
        state = self.listing()
        state = self.fx.saved(self.fx.action(state, 'confirm', 'reference_001'))
        state = self.fx.saved(self.fx.action(state, 'confirm', 'reference_002'))
        before = copy.deepcopy(state)
        calls = {p: p.read_bytes() for p in self.store.folder(state['id']).glob('calls/**/*') if p.is_file()}
        with patch('app.call_ai', side_effect=AssertionError('Manual must not call Planning')):
            edited = self.fx.saved(self.manual(state))
        self.assertEqual(edited['plans']['reference_001'], before['plans']['reference_001'])
        self.assertTrue(edited['plan_status']['reference_001']['confirmed'])
        self.assertFalse(edited['plan_status']['reference_002']['confirmed'])
        self.assertEqual(edited['plan_versions']['reference_002'], 2)
        self.assertEqual(edited['events'][-1]['source'], 'HUMAN_EDIT')
        self.assertEqual(edited['events'][-1]['before'], before['plans']['reference_002'])
        self.assertEqual(edited['events'][-1]['after'], edited['plans']['reference_002'])
        self.assertEqual({p: p.read_bytes() for p in calls}, calls)
        self.assertEqual(self.generate(edited, 'reference_002').status_code, 409)
        edited = self.fx.saved(self.fx.action(edited, 'confirm', 'reference_002'))
        with self.fx.fx.with_sdk():
            generated = self.generate(edited, 'reference_002')
        self.assertEqual(generated.status_code, 200)
        record = self.fx.fx.requests[-1].read()
        self.assertIn('0° / 15° / 25° / 40° / ミスト'.encode(), record)

    def test_manual_rejects_invalid_shape_length_target_and_stale_versions(self):
        state = self.listing(); before = self.fx.files(state)
        base = dict(action='manual_plan', target='reference_002', revision=state['revision'],
                    plan_version=1, plan=state['plans']['reference_002'])
        for change in [dict(plan={}), dict(plan={**base['plan'], 'goal': ' ' }),
                       dict(plan={**base['plan'], 'goal': 'x' * 12001}),
                       dict(plan={**base['plan'], 'unexpected': 'x'}), dict(target='reference_999'),
                       dict(plan_version=0), dict(revision=0)]:
            response = self.client.post(f"/api/sessions/{state['id']}/action", headers=HEADERS, json={**base, **change})
            self.assertIn(response.status_code, (400, 409))
        self.assertEqual(before, self.fx.files(state))

    def test_manual_keeps_unresolved_conflict_and_invalidates_resolved_scope(self):
        state = self.listing([self.fx.report()])
        edited = self.fx.saved(self.manual(state))
        self.assertTrue(blockers(edited, 'reference_002'))
        self.assertEqual(self.fx.action(edited, 'confirm', 'reference_002').status_code, 409)
        resolved = self.fx.saved(self.fx.action(edited, 'resolve_conflict',
            conflict_id=edited['fact_issues'][0]['conflict_id'], decision='RETAIN', note='人工决定，不是事实认证'))
        resolved = self.fx.saved(self.fx.action(resolved, 'confirm', 'reference_002'))
        edited = self.fx.saved(self.manual(resolved))
        self.assertEqual(issue_views(edited)[0]['resolution_status'], 'STALE')
        self.assertEqual(self.fx.action(edited, 'confirm', 'reference_002').status_code, 409)

    def test_manual_live_debug_is_free_even_without_key_and_quick_still_has_no_planning(self):
        state = self.listing()
        debug = app.create_local_debug_app(self.store.root, execution_mode='LIVE DEBUG',
                                           allow_runtime_tasks=True, allow_paid_actions=False).test_client()
        with patch.dict('os.environ', {'OPENAI_API_KEY': ''}), patch('app.call_ai', side_effect=AssertionError()):
            response = debug.post(f"/api/sessions/{state['id']}/action", headers=HEADERS,
                json=dict(action='manual_plan', target='reference_002', revision=state['revision'],
                          plan_version=1, plan=state['plans']['reference_002']))
        self.assertEqual(response.status_code, 200)
        quick = self.fx.saved(self.fx.create())
        self.assertEqual(self.fx.action(quick, 'manual_plan', 'reference_102', plan={}).status_code, 409)

    def test_quality_three_values_reach_actual_sdk_for_all_modes(self):
        observed = []
        for mode in ('quick_a', 'quick_b', 'listing'):
            state = self.fx.saved(self.fx.create(mode))
            if mode == 'listing':
                state = self.fx.saved(self.fx.plan(state))
                state = self.fx.saved(self.fx.action(state, 'confirm', 'reference_002'))
            target = 'reference_002' if mode == 'listing' else 'reference_102'
            for index, quality in enumerate(('low', 'medium', 'high')):
                state = self.fx.saved(self.quality(state, 'medium', {target: quality}))
                with self.fx.fx.with_sdk():
                    response = self.generate(state, target, edit=index > 0)
                self.assertEqual(response.status_code, 200, response.json)
                request = self.fx.fx.requests[-1]
                parts = BytesParser().parsebytes(('Content-Type: ' + request.headers['content-type'] + '\r\n\r\n').encode() + request.read()).get_payload()
                fields = {p.get_param('name', header='content-disposition'): p.get_payload(decode=True).decode()
                          for p in parts if not p.get_filename()}
                self.assertEqual(fields['quality'], quality)
                card = self.fx.card(state, target)
                folder = self.fx.fx.app.extensions['generation_service'].run_folder(state['id'], card['generation_revision'], target, response.json['run_id'])
                self.assertEqual(json.loads((folder / 'run.json').read_text())['parameters']['quality'], quality)
                self.assertEqual(json.loads((folder / 'request.json').read_text())['quality'], quality)
                observed.append((mode, quality))
            self.assertEqual(len(self.fx.card(state, target)['versions']), 3)
        self.assertEqual(len(observed), 9)

    def test_quality_preserves_plan_confirmation_parent_pass_and_other_output(self):
        state = self.listing(); state = self.fx.saved(self.fx.action(state, 'confirm', 'reference_002'))
        with self.fx.fx.with_sdk():
            original = self.generate(state, 'reference_002')
        self.assertEqual(self.review(state, 'pass').status_code, 200)
        before = self.fx.card(state, 'reference_002')
        state = self.fx.saved(self.quality(state, 'medium', {'reference_002': 'high'}))
        after = self.fx.card(state, 'reference_002')
        self.assertEqual(before['generation_revision'], after['generation_revision'])
        self.assertEqual(before['passed_run'], after['passed_run'])
        self.assertTrue(state['plan_status']['reference_002']['confirmed'])
        self.assertEqual(self.fx.card(state, 'reference_001')['quality'], 'medium')
        with self.fx.fx.with_sdk():
            modified = self.generate(state, 'reference_002', edit=True)
        self.assertEqual(modified.status_code, 200)
        self.assertEqual(self.fx.card(state, 'reference_002')['passed_run'], original.json['run_id'])
        self.assertEqual(self.fx.card(state, 'reference_002')['versions'][-1]['parent_run_id'], original.json['run_id'])

    def test_quality_invalid_values_ownership_and_stale_version_are_rejected(self):
        state = self.fx.saved(self.fx.create())
        before = self.fx.files(state)
        for value in ('auto', 'max', '', None, True):
            self.assertEqual(self.quality(state, value).status_code, 400)
        self.assertEqual(self.quality(state, overrides={'reference_999': 'high'}).status_code, 400)
        self.assertEqual(self.quality(state, quality_revision=99).status_code, 409)
        self.assertEqual(before, self.fx.files(state))
        state = self.fx.saved(self.quality(state))
        self.assertEqual(self.generate(state, 'reference_102', quality='high').status_code, 409)
        self.assertEqual(self.generate(state, 'reference_102', quality_revision=0).status_code, 409)
        self.assertEqual(self.fx.fx.requests, [])

    def test_quality_initial_creation_copy_restore_and_invalid_prewrite(self):
        state = self.fx.saved(self.fx.create())
        data = dict(title='Copy', mode='quick_redesign', quick_scenario='quick_a', quick_business_version='v1',
                    quick_slots=json.dumps(state['quick_slots']), from_session=state['id'],
                    keep_images=json.dumps([i['id'] for i in state['images']]), **state['inputs'],
                    generation_quality='medium', image_qualities=json.dumps({'reference_102': 'high'}))
        for quality in ('auto', 'standard'):
            before = sorted(p.name for p in (self.store.root / 'sessions').iterdir())
            self.assertEqual(self.client.post('/api/sessions', headers=HEADERS, data={**data, 'generation_quality': quality}).status_code, 400)
            self.assertEqual(before, sorted(p.name for p in (self.store.root / 'sessions').iterdir()))
        clone = self.fx.saved(self.client.post('/api/sessions', headers=HEADERS, data=data))
        self.assertEqual(self.store.load(clone['id'])['generation_quality'], 'medium')
        self.assertEqual(self.fx.card(clone, 'reference_102')['quality'], 'high')
        self.assertEqual(self.fx.card(state, 'reference_102').get('quality', 'low'), 'low')

    def test_same_operation_cannot_be_reused_for_changed_quality(self):
        state = self.fx.saved(self.fx.create()); op = uuid4().hex
        with self.fx.fx.with_sdk():
            self.assertEqual(self.generate(state, 'reference_102', operation=op).status_code, 200)
        state = self.fx.saved(self.quality(state, 'high'))
        self.assertEqual(self.generate(state, 'reference_102', operation=op).status_code, 409)
        self.assertEqual(len(self.fx.fx.requests), 1)

    def test_reject_retains_image_old_pass_feedback_and_export(self):
        state = self.fx.saved(self.fx.create())
        with self.fx.fx.with_sdk():
            first = self.generate(state, 'reference_102')
        self.assertEqual(self.review(state, 'pass', 'reference_102').status_code, 200)
        with self.fx.fx.with_sdk():
            second = self.generate(state, 'reference_102', edit=True)
        calls = len(self.fx.fx.requests)
        for reason in ('PRODUCT_FIDELITY', 'CLAIM_ERROR', 'REFERENCE_MISMATCH', 'DESIGN_QUALITY', 'TEXT_LAYOUT', 'OTHER'):
            response = self.review(state, 'reject', 'reference_102', reason=reason, note='保留商品接口，只调整文字')
            self.assertEqual(response.status_code, 200, response.json)
            event = response.json['event']
            self.assertEqual(event['run_id'], second.json['run_id'])
            self.assertEqual(event['reason'], reason)
            self.assertEqual(event['source'], 'HUMAN_REVIEW')
        card = self.fx.card(state, 'reference_102')
        self.assertEqual(card['passed_run'], first.json['run_id'])
        self.assertEqual(len(card['versions']), 2)
        self.assertEqual(card['review_events'][-1]['note'], '保留商品接口，只调整文字')
        self.assertEqual(len(self.fx.fx.requests), calls)
        self.assertFalse(self.fx.card(state, 'reference_101').get('review_events', []))
        exported = self.client.post(f"/api/sessions/{state['id']}/export-passed", headers=HEADERS)
        self.assertEqual(exported.status_code, 200)
        with zipfile.ZipFile(io.BytesIO(exported.data)) as z:
            self.assertEqual(len(z.namelist()), 1)
            self.assertIn('_V1.png', z.namelist()[0])

    def test_reject_invalid_scope_reason_stale_and_oversized_note_are_refused(self):
        state = self.fx.saved(self.fx.create())
        with self.fx.fx.with_sdk():
            generated = self.generate(state, 'reference_102')
        before = self.fx.files(state)
        for change in [dict(reason='UNKNOWN'), dict(reason=None), dict(note='x' * 12001),
                       dict(card_revision=0), dict(run_id='20261029T000000Z-' + '0' * 32)]:
            body = dict(reason='OTHER', note='匿名说明');body.update(change)
            self.assertEqual(self.review(state, 'reject', 'reference_102', **body).status_code, 409)
        self.assertEqual(before, self.fx.files(state))

    def test_quality_settings_are_exported_without_changing_prior_snapshot(self):
        state = self.listing(); folder = self.store.folder(state['id'])
        path = folder / 'versions' / f"{state['revision']:06}.json"; before = path.read_bytes()
        self.fx.saved(self.quality(state, 'high'))
        self.assertEqual(path.read_bytes(), before)
        package = self.client.post(f"/api/sessions/{state['id']}/export-experiment", headers=HEADERS)
        self.assertEqual(package.status_code, 200, package.json)
        with zipfile.ZipFile(io.BytesIO(package.data)) as z:
            self.assertTrue(any(name.endswith('/planning/generation_settings.json') for name in z.namelist()))

    def test_disabled_slot_quality_is_retained_without_becoming_an_output(self):
        state = self.fx.saved(self.fx.create())
        state = self.fx.saved(self.quality(state, 'medium', {'reference_101': 'high'}))
        raw = self.store.load(state['id'])
        raw['quick_slots'][0]['enabled'] = False
        self.store.save(raw, {'action': 'anonymous_fixture_only', 'target': None})
        state = self.fx.saved(self.quality(raw, 'low', {'reference_101': 'high'}))
        self.assertEqual(state['image_qualities']['reference_101'], 'high')
        cards = self.client.get(f"/api/sessions/{state['id']}/workspace").json['generation']['cards']
        self.assertEqual([card['id'] for card in cards], ['reference_102'])

    def test_free_quality_and_manual_actions_keep_existing_task_and_image_locks(self):
        state = self.listing(); before = self.fx.files(state)
        self.store.lock.acquire()
        try:
            self.assertEqual(self.quality(state).status_code, 409)
            self.assertEqual(self.manual(state).status_code, 409)
        finally:
            self.store.lock.release()
        service = self.fx.fx.app.extensions['generation_service']
        service.active.add((state['id'], state['revision'], 'reference_002'))
        try:
            self.assertEqual(self.quality(state).status_code, 409)
            self.assertEqual(self.manual(state).status_code, 409)
        finally:
            service.active.clear()
        self.assertEqual(before, self.fx.files(state))

    def test_quality_settings_ownership_is_checked_and_inspector_reads_actual_run_quality(self):
        from api.inspector import create_inspector_app
        state = self.fx.saved(self.fx.create())
        state = self.fx.saved(self.quality(state, 'high'))
        with self.fx.fx.with_sdk():
            generated = self.generate(state, 'reference_102')
        self.assertEqual(generated.status_code, 200)
        card = self.fx.card(state, 'reference_102')
        inspector = create_inspector_app(self.store.root, [state['id']]).test_client()
        response = inspector.get(f"/api/inspector/tasks/{state['id']}", query_string=dict(
            image_id='reference_102', revision=card['generation_revision'], run_id=generated.json['run_id']))
        self.assertEqual(response.status_code, 200)
        self.assertIn('high', json.dumps(response.json))
        settings = self.store.folder(state['id']) / 'generation_settings.json'
        value = json.loads(settings.read_text()); value['task_id'] = 'f' * 32
        settings.write_text(json.dumps(value))
        self.assertEqual(self.client.get(f"/api/sessions/{state['id']}").status_code, 409)
