"""Anonymous regressions derived from Call 79ac7dbd03df48478f4ddf04892c9881.

Preserve its two failure shapes, not operational images/text or a runtime dependency.
Corrected copies below are synthetic test outputs, never a repaired historical call.
"""

import copy
import json
import unittest

import httpx
import test_business_guards as guards
from image_workflow import Problem
from image_workflow.planning import conflicts, validation
from image_workflow.planning.request import build_planning_request


IDS = ['reference_001', 'reference_002']
BRIEF = '本图仅使用已提供的功能，不增加未确认机构。'


def sample():
    images = [dict(id=key, role=role, name=key + '.png', file=f'inputs/{key}.png', mime='image/png')
              for role, keys in [('product', ['product_001', 'product_002', 'product_003']),
                                 ('reference', IDS)] for key in keys]
    slots = [dict(id='reference_101', type='main', enabled=True, reference_id=IDS[0],
                  requirements='只展示真实商品外观。', output_size='1024x1536'),
             dict(id='reference_102', type='selling_point', enabled=True, reference_id=IDS[1],
                  requirements=BRIEF, output_size='1024x1024')]
    state = dict(images=images, listing_slots=slots, inputs=dict(listing='匿名商品宣称。',
                 description='匿名附件随附。', requirements='日语风格。'), product=None,
                 references={}, plans={}, corrections=dict(product=[], references={}),
                 product_version=0, reference_versions={}, plan_versions={})
    result = dict(product={key: '匿名候选理解，未经认证' for key in validation.PRODUCT_FIELDS},
                  references={key: {field: '匿名参考理解' for field in validation.REFERENCE_FIELDS} for key in IDS},
                  plans={key: {field: '匿名制作计划' for field in validation.PLAN_FIELDS} for key in IDS})
    # Same defects as the real response: Brief attributed to original requirements,
    # and output-slot IDs mixed into affected reference/plan IDs.
    result['fact_issues'] = [dict(conflict_id='fi_001', affected_claim='本次允许的功能是否可见',
        text_evidence=dict(source='requirements', quote=BRIEF),
        visual_evidence=dict(product_image_ids=['product_002', 'product_003'], observation='当前角度不能确认功能'),
        issue_type='INSUFFICIENT_EVIDENCE', affected_image_ids=['reference_002', 'reference_102']),
        dict(conflict_id='fi_002', affected_claim='匿名附件是否随附',
        text_evidence=dict(source='description', quote='匿名附件随附。'),
        visual_evidence=dict(product_image_ids=['product_001'], observation='可见附件，不能证明包装配置'),
        issue_type='INSUFFICIENT_EVIDENCE', affected_image_ids=IDS + ['reference_101', 'reference_102'])]
    return state, result


def valid_sample():
    state, raw = sample()
    raw['fact_issues'][0]['text_evidence'] = dict(source='slot_requirements', reference_id=IDS[1], quote=BRIEF)
    raw['fact_issues'][0]['affected_image_ids'] = [IDS[1]]
    raw['fact_issues'][1]['affected_image_ids'] = IDS.copy()
    return state, raw


def request_context(state, action='understand', target=None):
    arguments, _ = build_planning_request(state, action, target, '', 'offline-model',
        {image['file']: b'anonymous-fixture' for image in state['images']},
        reasoning_model='offline-model')
    return json.loads(arguments['input'][0]['content'][0]['text'])


class ListingContractTests(unittest.TestCase):
    def test_failure_shape_still_rejected_without_mutating_response(self):
        state, raw = sample(); before = copy.deepcopy(raw)
        with self.assertRaises(Problem):
            conflicts.validate_reports(raw, state, IDS)
        self.assertEqual(raw, before)

    def test_correcting_only_ids_does_not_legalize_wrong_source(self):
        state, raw = sample()
        for item in raw['fact_issues']:
            item['affected_image_ids'] = [key for key in item['affected_image_ids'] if key in IDS]
        with self.assertRaises(Problem):
            conflicts.validate_reports(raw, state, IDS)

    def test_correcting_only_source_does_not_legalize_slot_ids(self):
        state, raw = sample()
        raw['fact_issues'][0]['text_evidence'] = dict(source='slot_requirements', reference_id=IDS[1], quote=BRIEF)
        with self.assertRaises(Problem):
            conflicts.validate_reports(raw, state, IDS)

    def test_explicit_reference_ids_and_exact_slot_source_validate(self):
        state, raw = valid_sample()
        self.assertEqual(set(validation.validate_result(raw, 'understand', IDS)['plans']), set(IDS))
        self.assertEqual(conflicts.validate_reports(raw, state, IDS), raw['fact_issues'])

    def test_wrong_plan_or_reference_keys_remain_invalid(self):
        for group in ('plans', 'references'):
            _, raw = valid_sample(); raw[group]['reference_101'] = raw[group].pop(IDS[0])
            with self.assertRaises(Problem):
                validation.validate_result(raw, 'understand', IDS)

    def test_original_text_sources_keep_exact_match_and_attribution(self):
        for source in ('listing', 'description', 'requirements'):
            state, raw = valid_sample(); raw['fact_issues'] = [raw['fact_issues'][1]]
            text = raw['fact_issues'][0]['text_evidence']
            text.update(source=source, quote=state['inputs'][source])
            self.assertEqual(conflicts.validate_reports(raw, state, IDS), raw['fact_issues'])
            text['quote'] += '未经提供的扩写'
            with self.assertRaises(Problem):
                conflicts.validate_reports(raw, state, IDS)

    def test_slot_source_rejects_foreign_product_disabled_and_unaffected_reference(self):
        for reference in ('reference_999', 'reference_102', 'product_001', IDS[0]):
            state, raw = valid_sample(); raw['fact_issues'][0]['text_evidence']['reference_id'] = reference
            with self.assertRaises(Problem):
                conflicts.validate_reports(raw, state, IDS)
        state, raw = valid_sample(); state['listing_slots'][1]['enabled'] = False
        with self.assertRaises(Problem):
            conflicts.validate_reports(raw, state, IDS)

    def test_slot_quote_and_source_type_cannot_be_guessed_or_normalized(self):
        for change in (dict(quote='编造的约束'), dict(source='model_inference'), dict(source='reference_image'),
                       dict(source='requirements'), dict(reference_id=None)):
            state, raw = valid_sample(); raw['fact_issues'][0]['text_evidence'].update(change)
            with self.assertRaises(Problem):
                conflicts.validate_reports(raw, state, IDS)

    def test_slot_source_must_be_in_this_calls_input_scope(self):
        state, raw = valid_sample()
        with self.assertRaises(Problem):
            conflicts.validate_reports(raw, state, IDS, slot_reference_ids=[IDS[0]])

    def test_request_omits_internal_slot_identity_and_preserves_saved_configuration(self):
        state, _ = sample(); before = copy.deepcopy(state); context = request_context(state)
        self.assertEqual(context['planning_id_contract']['valid_reference_ids'], IDS)
        for key, slot in context['output_slot_inputs'].items():
            self.assertEqual(slot, {name: value for name, value in state['listing_slots'][IDS.index(key)].items() if name != 'id'})
        self.assertNotIn('reference_101', json.dumps(context))
        self.assertNotIn('reference_102', json.dumps(context))
        self.assertEqual(state, before)

    def test_source_contract_distinguishes_original_text_slot_brief_and_inference(self):
        state, _ = sample(); context = request_context(state)
        sources = context['fact_source_contract']
        self.assertEqual(sources['original_text_sources'], ['listing', 'description', 'requirements'])
        self.assertEqual(sources['slot_requirements_reference_ids'], IDS)
        self.assertIn('模型推断', context['fact_review_instructions'])
        self.assertIn('制作约束', context['fact_review_instructions'])
        # Forbidden product-specific claims remain caller data, not global rules.
        self.assertNotIn('10MPa', context['fact_review_instructions'])
        self.assertNotIn('760g', context['fact_review_instructions'])

    def test_targeted_and_product_only_calls_do_not_expose_unread_slot_sources(self):
        state, _ = sample(); context = request_context(state, 'plan', IDS[1])
        self.assertEqual(list(context['output_slot_inputs']), [IDS[1]])
        self.assertEqual(context['fact_source_contract']['slot_requirements_reference_ids'], [IDS[1]])
        context = request_context(state, 'product')
        self.assertNotIn('output_slot_inputs', context)
        self.assertEqual(context['fact_source_contract']['slot_requirements_reference_ids'], [])

    def test_new_source_resolution_scope_tracks_brief_without_changing_legacy_digest(self):
        state, raw = valid_sample(); issue = raw['fact_issues'][0]
        old = conflicts.scope(state, issue)
        state['listing_slots'][1]['requirements'] += '新版本约束'
        self.assertNotEqual(conflicts.scope(state, issue), old)
        old = conflicts.scope(state, raw['fact_issues'][1])
        state['listing_slots'][1]['requirements'] += '另一个版本'
        self.assertEqual(conflicts.scope(state, raw['fact_issues'][1]), old)


class ListingContractIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.helper = guards.BusinessGuardTests(); self.helper.setUp()
        self.addCleanup(self.helper.doCleanups)
        seed, self.raw = valid_sample()
        self.state = self.helper.store.create(seed['inputs'],
            [(image['role'], image['name'], guards.generation_fixture.png()) for image in seed['images']],
            'anonymous contract fixture', listing_slots=seed['listing_slots'])

    def planning(self, state, raw, action='understand', target=None):
        def response(body, _):
            return httpx.Response(200, json=dict(id='resp_anonymous_contract', model=body['model'], status='completed',
                output=[dict(type='message', id='msg_contract', role='assistant', status='completed',
                content=[dict(type='output_text', text=json.dumps(raw), annotations=[])])]))
        with self.helper.planner.with_ai(response):
            return self.helper.action(state, action, target, feedback='匿名计划修订' if target else '')

    def test_rejected_output_is_preserved_and_never_applied(self):
        _, bad = sample(); before = self.helper.store.load(self.state['id'])
        response = self.planning(self.state, bad)
        self.assertEqual(response.status_code, 502)
        self.assertEqual(self.helper.store.load(self.state['id']), before)
        call = next((self.helper.store.folder(self.state['id']) / 'calls').iterdir())
        saved = json.loads((call / 'response.json').read_text())
        self.assertEqual(json.loads(saved['output'][0]['content'][0]['text']), bad)
        self.assertTrue((call / 'error.json').exists())

    def test_insufficient_evidence_preserves_explicit_per_image_confirmation(self):
        state = self.helper.saved(self.planning(self.state, self.raw))
        self.assertFalse(conflicts.blockers(state, IDS[1]))
        self.assertFalse(state['plan_status'][IDS[1]]['confirmed'])
        self.assertEqual(self.helper.generate(state, IDS[1]).status_code, 409)
        confirmed = self.helper.saved(self.helper.action(state, 'confirm', IDS[1]))
        self.assertTrue(confirmed['plan_status'][IDS[1]]['confirmed'])
        self.assertFalse(confirmed['plan_status'][IDS[0]]['confirmed'])
        self.assertEqual(self.helper.fx.requests, [])

    def test_targeted_call_cannot_cite_a_slot_brief_it_did_not_receive(self):
        state = self.helper.saved(self.planning(self.state, self.raw))
        before = self.helper.store.load(state['id'])
        # Only reference_001's inputs are supplied for this plan operation.
        output = dict(plan=self.raw['plans'][IDS[0]], fact_issues=[self.raw['fact_issues'][0]])
        response = self.planning(state, output, 'plan', IDS[0])
        self.assertEqual(response.status_code, 502)
        self.assertEqual(self.helper.store.load(state['id']), before)
        self.assertEqual(self.helper.fx.requests, [])

    def test_visible_slot_report_blocks_old_confirmation_until_resolution_and_reconfirmation(self):
        state = self.helper.saved(self.planning(self.state, self.raw))
        state = self.helper.saved(self.helper.action(state, 'confirm', IDS[1]))
        report = copy.deepcopy(self.raw['fact_issues'][0]); report['issue_type'] = 'VISIBLE_CONTRADICTION'
        revised = dict(plan=self.raw['plans'][IDS[1]], fact_issues=[report])
        state = self.helper.saved(self.planning(state, revised, 'plan', IDS[1]))
        self.assertEqual(self.helper.action(state, 'confirm', IDS[1]).status_code, 409)
        self.assertEqual(self.helper.generate(state, IDS[1]).status_code, 409)
        state = self.helper.saved(self.helper.action(state, 'resolve_conflict',
            conflict_id=state['fact_issues'][-1]['conflict_id'], decision='RETAIN', note='匿名人工决定，非事实认证'))
        self.assertFalse(state['plan_status'][IDS[1]]['confirmed'])
        self.assertEqual(self.helper.generate(state, IDS[1]).status_code, 409)
        state = self.helper.saved(self.helper.action(state, 'confirm', IDS[1]))
        self.assertTrue(state['plan_status'][IDS[1]]['confirmed'])
        self.assertEqual(self.helper.fx.requests, [])
