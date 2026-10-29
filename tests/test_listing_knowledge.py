"""B-02: actual Responses SDK Mock serialization and temporary Call Evidence."""

import copy
import base64
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import httpx
import app
from file_ops import sha256
from image_workflow.knowledge import load_registry
from image_workflow.planning.knowledge import HEADER, prepare_knowledge
from image_workflow.planning.request import planning_images
import test_prepare_plan as fixtures
from test_generate_plan_image import png


def condition(name, source, value=True):
    return {'condition': name, 'value': value, 'sources': source}


class ListingKnowledgeTests(unittest.TestCase):
    def setUp(self):
        self.fx = fixtures.PreparePlanTests()
        self.fx.setUp()
        self.addCleanup(self.fx.doCleanups)
        self.addCleanup(self.fx.tearDown)
        self.enterContext(patch('socket.socket.connect', side_effect=AssertionError('No network')))
        self.store = self.fx.app.extensions['plan_store']
        self.client = self.fx.client
        self.state = self.create()
        self.registry = load_registry()

    def create(self, count=3, classified=True):
        rows = [dict(id=f'reference_{101+i}', type='scene' if i == 1 else 'selling_point', enabled=True,
                     reference_id=f'reference_{i+1:03}', requirements=f'手机端阅读；保留文案：本图要求{i+1}。',
                     output_size='1024x1536') for i in range(count)]
        return self.store.create({'listing': '接口为 USB-C；资料声称 2WAY，未经独立认证。',
            'description': '具有两个工作状态的资料声明，需要人工核对。', 'requirements': '使用日语，保留指定文案。'},
            [('product', f'own-{i}.png', png((24+i, 32))) for i in range(2)] +
            [('reference', f'reference-{i}.png', png((32+i, 40))) for i in range(count)],
            'NEW ANONYMOUS B-02 FIXTURE', **({'listing_slots': rows} if classified else {}))

    def post(self, state=None, kind='understand', target=None, **options):
        state = self.state if state is None else state
        return self.client.post(f"/api/sessions/{state['id']}/action", headers=fixtures.HEADERS,
            json=dict(action=kind, revision=state['revision'], target=target,
                      feedback='仅调整本图的制作方向' if kind in ('plan', 'product', 'reference') else '', **options))

    def run_call(self, state=None, kind='understand', target=None, handler=None, **options):
        before = len(self.fx.requests)
        with self.fx.with_ai(handler) as factory:
            response = self.post(state, kind, target, **options)
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(len(self.fx.requests) - before, 1)
        self.assertEqual(factory.call_args.kwargs['max_retries'], 0)
        self.assertEqual(factory.call_args.kwargs['timeout'], 120.0)
        return response.json['state']

    def folder(self, state):
        call = next(event['call_id'] for event in reversed(state['events']) if 'call_id' in event)
        return self.store.folder(state['id']) / 'calls' / call

    def latest_folder(self, state=None):
        state = self.state if state is None else state
        return max((self.store.folder(state['id']) / 'calls').iterdir(), key=lambda path: path.stat().st_mtime_ns)

    def k01(self, *, detail=True, value=True):
        rows = [condition('visible_component', [{'source': 'product_image', 'image_id': 'product_001'}], value),
                condition('component_description', [{'source': 'listing', 'quote': '接口为 USB-C'}])]
        if detail:
            rows.append(condition('product_detail_view', [{'source': 'product_image', 'image_id': 'product_002'}]))
        return rows

    def k05(self, index=1):
        return [condition('multiple_information_items', [{'source': 'listing', 'quote': '接口为 USB-C；资料声称 2WAY'}]),
                condition('required_content_known', [{'source': 'slot_requirements', 'quote': f'保留文案：本图要求{index}。'}])]

    def k06(self, index=1):
        return [condition('readability_target', [{'source': 'slot_requirements', 'quote': '手机端阅读'}]),
                condition('copy_and_size_available', [{'source': 'slot_requirements', 'quote': f'保留文案：本图要求{index}。'},
                                                       {'source': 'output_size', 'value': '1024x1536'}])]

    def evidence(self, state):
        folder = self.folder(state)
        knowledge = json.loads((folder / 'knowledge.json').read_text())
        request = json.loads((folder / 'request.json').read_text())
        run = json.loads((folder / 'run.json').read_text())
        self.assertEqual(request, self.fx.requests[-1])
        texts = [item['text'] for item in request['input'][0]['content'] if item['type'] == 'input_text']
        self.assertEqual((folder / 'prompt.txt').read_text(), request['instructions'] + '\n\n' + '\n\n'.join(texts))
        actual = knowledge['effective_knowledge_text']
        self.assertEqual(texts.count(actual), 1 if actual else 0)
        self.assertEqual(knowledge['effective_knowledge_text_sha256'], sha256(actual.encode()))
        self.assertEqual(run['knowledge_text_sha256'], knowledge['effective_knowledge_text_sha256'])
        self.assertEqual(knowledge['request_payload_sha256'], sha256(json.dumps(request, ensure_ascii=False, sort_keys=True).encode()))
        self.assertEqual((knowledge['planning_call_id'], knowledge['task_id'], knowledge['parent_revision']),
                         (folder.name, state['id'], run['parent_revision']))
        self.assertEqual((knowledge['model'], knowledge['parameters']), (request['model'], run['parameters']))
        self.assertEqual(knowledge['model_adoption_status'], 'MODEL_ADOPTION_UNKNOWN')
        self.assertEqual((run['max_retries'], run['timeout_seconds']), (0, 120.0))
        if actual:
            chapter = json.loads(actual.removeprefix(HEADER))
            self.assertEqual([item['method_id'] for item in chapter['methods']], knowledge['method_ids'])
            for item in chapter['methods']:
                card = self.registry.get(item['method_id'], version=item['method_version'])
                self.assertEqual(item['card'], card.to_dict())
                self.assertEqual(item['content_hash'], card.content_hash)
                self.assertEqual(knowledge['source_references'][item['method_id']], card.source_reference.to_dict())
                self.assertEqual(knowledge['content_hashes'][item['method_id']], card.content_hash)
        return knowledge, request, folder

    def test_default_and_explicit_false_requests_remain_identical_without_knowledge_records(self):
        for explicit in (False, True):
            state = self.state if not explicit else self.create()
            before = copy.deepcopy(state)
            images = {image['file']: (self.store.folder(state['id']) / image['file']).read_bytes() for image in state['images']}
            expected, _ = app.build_planning_request(state, 'understand', None, '', 'gpt-4.1-mini', images)
            with patch('image_workflow.planning.knowledge.load_registry', side_effect=AssertionError('Disabled means no load')):
                result = self.run_call(state, **({'knowledge_enabled': False} if explicit else {}))
            folder = self.folder(result)
            self.assertEqual(self.fx.requests[-1], expected)
            self.assertFalse((folder / 'knowledge.json').exists())
            self.assertNotIn('knowledge_enabled', json.loads((folder / 'run.json').read_text()))
            self.assertEqual(state, before)

    def test_opt_in_without_structured_conditions_keeps_unknown_and_model_only(self):
        state = self.run_call(knowledge_enabled=True)
        knowledge, request, _ = self.evidence(state)
        self.assertEqual(knowledge['status'], 'NO_METHOD_SELECTED')
        self.assertEqual(knowledge['method_ids'], [])
        self.assertEqual(knowledge['effective_knowledge_text'], '')
        self.assertFalse(any(item.get('text', '').startswith(HEADER) for item in request['input'][0]['content']))
        for selected in knowledge['selection_basis'].values():
            self.assertEqual(selected['selected'], [])
            self.assertEqual({row['eligibility'] for row in selected['not_selected']}, {'CONDITIONAL'})

    def test_selected_card_reaches_actual_sdk_with_registry_identity_and_hash(self):
        state = self.run_call(knowledge_enabled=True, knowledge_conditions={'reference_001': self.k01()})
        knowledge, request, _ = self.evidence(state)
        self.assertEqual(knowledge['method_ids'], ['K01'])
        self.assertEqual(knowledge['applicable_reference_ids'], ['reference_001'])
        self.assertEqual(knowledge['eligibility']['K01'][0]['eligibility'], 'ELIGIBLE')
        current = json.loads(request['input'][0]['content'][0]['text'])
        self.assertEqual(current['original_inputs'], self.state['inputs'])
        self.assertEqual(current['planning_id_contract']['valid_reference_ids'], ['reference_001', 'reference_002', 'reference_003'])
        self.assertEqual(set(current['return_json']['plans']['reference_001']),
                         {'goal', 'selling_points', 'design', 'scene_style', 'risks'})
        expected = planning_images(self.state, 'understand', None)
        image_order = json.loads((self.folder(state) / 'image_order.json').read_text())
        self.assertEqual([row['id'] for row in image_order], [row['id'] for row in expected])
        actual_images = [item for item in request['input'][0]['content'] if item['type'] == 'input_image']
        self.assertEqual(len(actual_images), len(expected))
        for actual, image in zip(actual_images, expected):
            data = base64.b64decode(actual['image_url'].split(',', 1)[1])
            self.assertEqual(sha256(data), image['sha256'])
            self.assertEqual(data, (self.store.folder(self.state['id']) / image['file']).read_bytes())
        original_request, _ = app.build_planning_request(self.state, 'understand', None, '', request['model'],
            {image['file']: (self.store.folder(self.state['id']) / image['file']).read_bytes() for image in expected})
        without_chapter = copy.deepcopy(request)
        without_chapter['input'][0]['content'] = [item for item in without_chapter['input'][0]['content']
                                                if not item.get('text', '').startswith(HEADER)]
        self.assertEqual(without_chapter, original_request)
        sources = knowledge['selection_basis']['reference_001']['condition_sources']
        self.assertEqual({row['authority'] for row in sources}, {'OPERATOR_DECLARED_FOR_THIS_CALL_NOT_INDEPENDENTLY_VERIFIED'})

    def test_conditional_method_retains_missing_conditions_in_actual_chapter(self):
        state = self.run_call(knowledge_enabled=True, knowledge_conditions={'reference_001': self.k01(detail=False)})
        knowledge, _, _ = self.evidence(state)
        row = knowledge['eligibility']['K01'][0]
        self.assertEqual(row['eligibility'], 'CONDITIONAL')
        self.assertEqual(row['missing_conditions'], ['product_detail_view'])
        self.assertIn('CONDITIONAL 必须先检查素材是否支持', knowledge['effective_knowledge_text'])

    def test_excluded_method_body_is_not_injected(self):
        state = self.run_call(knowledge_enabled=True, knowledge_conditions={'reference_001': self.k01(value=False)})
        knowledge, _, _ = self.evidence(state)
        self.assertEqual(knowledge['method_ids'], [])
        row = next(row for row in knowledge['selection_basis']['reference_001']['not_selected'] if row['method_id'] == 'K01')
        self.assertEqual(row['eligibility'], 'EXCLUDED')
        self.assertEqual(knowledge['effective_knowledge_text'], '')

    def test_prior_unconfirmed_model_text_cannot_turn_unknown_conditions_true(self):
        state = self.run_call()
        state = self.run_call(state, 'replan', knowledge_enabled=True)
        knowledge, _, _ = self.evidence(state)
        self.assertEqual(knowledge['method_ids'], [])
        self.assertTrue(state['plans'])

    def test_budget_trims_whole_cards_and_retains_selection_and_omission_reasons(self):
        state = self.run_call(knowledge_enabled=True, knowledge_conditions={'reference_001': self.k01() + self.k05() + self.k06()},
                              knowledge_char_budget=900)
        knowledge, _, _ = self.evidence(state)
        self.assertLessEqual(len(knowledge['effective_knowledge_text']), 900)
        self.assertEqual(len(knowledge['selection_basis']['reference_001']['selected']), 3)
        self.assertTrue(knowledge['budget_omissions'])
        self.assertEqual({row['reason'] for row in knowledge['budget_omissions']}, {'CONTENT_BUDGET'})
        for row in knowledge['budget_omissions']:
            self.assertNotIn(row['method_id'], knowledge['method_ids'])

    def test_dynamic_n_deduplicates_method_body_without_sharing_other_slot_conditions(self):
        source = self.create(count=10)
        conditions = {f'reference_{i+1:03}': self.k05(i+1) for i in range(9)}
        state = self.run_call(source, knowledge_enabled=True, knowledge_conditions=conditions)
        knowledge, _, _ = self.evidence(state)
        self.assertEqual(knowledge['method_ids'], ['K05'])
        methods = json.loads(knowledge['effective_knowledge_text'].removeprefix(HEADER))['methods']
        self.assertEqual(len(methods), 1)
        self.assertEqual(len(methods[0]['applications']), 9)
        self.assertNotIn('reference_010', knowledge['applicable_reference_ids'])
        self.assertEqual(knowledge['selection_basis']['reference_010']['selected'], [])
        for i in range(9):
            quote = knowledge['selection_basis'][f'reference_{i+1:03}']['condition_sources'][1]['sources'][0]['quote']
            self.assertEqual(quote, f'保留文案：本图要求{i+1}。')

    def test_single_plan_call_only_uses_its_reference_and_settings_do_not_persist(self):
        state = self.run_call()
        state = self.run_call(state, 'plan', 'reference_002', knowledge_enabled=True,
                              knowledge_conditions={'reference_002': self.k06(2)})
        knowledge, request, _ = self.evidence(state)
        self.assertEqual(knowledge['method_ids'], ['K06'])
        self.assertEqual(list(knowledge['selection_basis']), ['reference_002'])
        images = json.loads((self.folder(state) / 'image_order.json').read_text())
        self.assertEqual([image['id'] for image in images if image['role'] == 'reference'], ['reference_002'])
        state = self.run_call(state, 'plan', 'reference_002')
        self.assertFalse((self.folder(state) / 'knowledge.json').exists())
        self.assertNotIn('knowledge_enabled', state)
        self.assertNotIn('knowledge_conditions', state)

    def test_invalid_switch_budget_or_disabled_conditions_are_rejected_without_call(self):
        variants = [dict(knowledge_enabled=value) for value in ('true', 'false', 0, 1, None)]
        variants += [dict(knowledge_enabled=True, knowledge_char_budget=value) for value in (True, 0, 255, 12001, '900')]
        variants += [dict(knowledge_conditions={}), dict(knowledge_enabled=True, knowledge_conditions=[])]
        for options in variants:
            with self.subTest(options=options):
                self.assertEqual(self.post(**options).status_code, 400)
        self.assertEqual(self.fx.requests, [])
        self.assertFalse((self.store.folder(self.state['id']) / 'calls').exists())

    def test_foreign_slot_product_role_source_and_quote_are_rejected_before_sdk(self):
        variants = [{'reference_101': self.k01()}, {'reference_999': self.k01()}]
        for source in ({'source': 'product_image', 'image_id': 'reference_001'},
                       {'source': 'product_image', 'image_id': 'product_999'},
                       {'source': 'file', 'path': '../../outside'},
                       {'source': 'model_inference', 'quote': '2WAY'},
                       {'source': 'listing', 'quote': '未提供的内容'}):
            variants.append({'reference_001': [condition('visible_component', [source])]})
        variants.append({'reference_001': [condition('required_content_known',
                         [{'source': 'slot_requirements', 'quote': '本图要求2'}])]})
        original = (self.store.folder(self.state['id']) / 'state.json').read_bytes()
        for declarations in variants:
            response = self.post(knowledge_enabled=True, knowledge_conditions=declarations)
            self.assertEqual(response.status_code, 400, response.json)
        self.assertEqual(self.fx.requests, [])
        self.assertEqual((self.store.folder(self.state['id']) / 'state.json').read_bytes(), original)

    def test_true_requires_sources_and_size_alone_does_not_prove_readability_or_copy(self):
        rows = [condition('multiple_states_supported', []),
                condition('readability_target', [{'source': 'output_size', 'value': '1024x1536'}]),
                condition('copy_and_size_available', [{'source': 'output_size', 'value': '1024x1536'}]),
                condition('visible_component', [{'source': 'listing', 'quote': '接口为 USB-C'}])]
        for row in rows:
            self.assertEqual(self.post(knowledge_enabled=True, knowledge_conditions={'reference_001': [row]}).status_code, 400)
        self.assertEqual(self.fx.requests, [])

    def test_unknown_and_explicit_negative_conditions_are_not_coerced(self):
        declarations = {'reference_001': [condition('multiple_states_supported', [], None),
                                         condition('usage_scene_supported', [{'source': 'description', 'quote': '需要人工核对'}], False)]}
        state = self.run_call(knowledge_enabled=True, knowledge_conditions=declarations)
        knowledge, _, _ = self.evidence(state)
        rows = {row['method_id']: row for row in knowledge['selection_basis']['reference_001']['not_selected']}
        self.assertEqual(rows['K02']['eligibility'], 'CONDITIONAL')
        self.assertEqual(rows['K03']['eligibility'], 'EXCLUDED')

    def test_failed_api_keeps_request_knowledge_and_error_with_one_attempt(self):
        before = (self.store.folder(self.state['id']) / 'state.json').read_bytes()
        def fail(body, result):
            return httpx.Response(400, json={'error': {'message': 'anonymous rejection', 'type': 'invalid_request_error'}},
                                  headers={'x-request-id': 'req_knowledge_mock_failure'})
        with self.fx.with_ai(fail):
            response = self.post(knowledge_enabled=True, knowledge_conditions={'reference_001': self.k01()})
        self.assertEqual(response.status_code, 502)
        self.assertEqual(len(self.fx.requests), 1)
        folder = self.latest_folder()
        knowledge = json.loads((folder / 'knowledge.json').read_text())
        self.assertEqual(knowledge['planning_status'], 'FAILED')
        self.assertTrue(knowledge['api_call_attempted'])
        self.assertEqual(knowledge['method_ids'], ['K01'])
        self.assertTrue((folder / 'request.json').is_file())
        self.assertTrue((folder / 'error.json').is_file())
        self.assertFalse((folder / 'result.json').exists())
        self.assertEqual((self.store.folder(self.state['id']) / 'state.json').read_bytes(), before)

    def test_custom_builder_cannot_silently_drop_selected_chapter(self):
        original = app.build_planning_request
        def omit(*args, **options):
            return original(*args)
        with patch.object(app, 'build_planning_request', side_effect=omit):
            response = self.post(knowledge_enabled=True, knowledge_conditions={'reference_001': self.k01()})
        self.assertEqual(response.status_code, 400)
        self.assertIn('未完整包含', response.json['error'])
        self.assertEqual(self.fx.requests, [])
        self.assertTrue((self.latest_folder() / 'knowledge.json').is_file())

    def test_no_candidate_cannot_be_replaced_with_an_unrecorded_method_chapter(self):
        original = app.build_planning_request
        def inject(*args, **options):
            arguments, order = original(*args)
            arguments['input'][0]['content'].append({'type': 'input_text', 'text': HEADER + 'unrecorded method'})
            return arguments, order
        with patch.object(app, 'build_planning_request', side_effect=inject):
            response = self.post(knowledge_enabled=True)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.fx.requests, [])

    def test_effective_prompt_uses_actual_request_instructions_and_adoption_stays_unknown(self):
        original = app.build_planning_request
        def augment(*args, **options):
            arguments, order = original(*args, **options)
            arguments['instructions'] += '\n匿名测试：保持原五字段输出。'
            return arguments, order
        def mentions_method(body, result):
            result['plans']['reference_001']['design'] = '文字自述采用 K01，不构成可靠的结构化采用证据。'
            return self.response(body, result)
        with patch.object(app, 'build_planning_request', side_effect=augment):
            state = self.run_call(handler=mentions_method, knowledge_enabled=True,
                                  knowledge_conditions={'reference_001': self.k01()})
        knowledge, _, _ = self.evidence(state)
        self.assertEqual(knowledge['model_adoption_status'], 'MODEL_ADOPTION_UNKNOWN')

    def test_knowledge_persistence_failure_stops_before_sdk_and_retains_failed_run(self):
        original = app.write_json
        failed = False
        def deny_once(path, value, exclusive=False):
            nonlocal failed
            if path.name == 'knowledge.json' and not failed:
                failed = True
                raise OSError('anonymous fixture write failure')
            return original(path, value, exclusive=exclusive)
        with patch.object(app, 'write_json', side_effect=deny_once):
            response = self.post(knowledge_enabled=True, knowledge_conditions={'reference_001': self.k01()})
        self.assertEqual(response.status_code, 502)
        self.assertEqual(self.fx.requests, [])
        folder = self.latest_folder()
        self.assertEqual(json.loads((folder / 'run.json').read_text())['status'], 'FAILED')
        self.assertFalse(json.loads((folder / 'run.json').read_text())['api_call_attempted'])
        self.assertEqual(json.loads((folder / 'knowledge.json').read_text())['status'], 'PREPARATION_FAILED')
        self.assertTrue((folder / 'error.json').exists())

    def test_wrong_model_plan_identity_is_still_rejected_without_remapping(self):
        def wrong_id(body, result):
            result['plans']['reference_101'] = result['plans'].pop('reference_001')
            return self.response(body, result)
        with self.fx.with_ai(wrong_id):
            response = self.post(knowledge_enabled=True, knowledge_conditions={'reference_001': self.k01()})
        self.assertEqual(response.status_code, 502)
        self.assertEqual(len(self.fx.requests), 1)
        self.assertIsNone(self.store.load(self.state['id'])['product'])
        self.assertTrue((self.latest_folder() / 'response.json').exists())

    def test_knowledge_is_not_a_legal_product_fact_source(self):
        def bad_source(body, result):
            result['fact_issues'] = [self.issue('PROFESSIONAL_METHOD')]
            return self.response(body, result)
        with self.fx.with_ai(bad_source):
            response = self.post(knowledge_enabled=True, knowledge_conditions={'reference_001': self.k01()})
        self.assertEqual(response.status_code, 502)
        self.assertEqual(len(self.fx.requests), 1)
        self.assertTrue((self.latest_folder() / 'response.json').is_file())
        self.assertIsNone(self.store.load(self.state['id'])['product'])

    def issue(self, source='listing'):
        return dict(conflict_id='connector', affected_claim='接口为 USB-C',
            text_evidence=dict(source=source, quote='接口为 USB-C'),
            visual_evidence=dict(product_image_ids=['product_001'], observation='匿名 Mock 可见接口与文字不同'),
            issue_type='VISIBLE_CONTRADICTION', affected_image_ids=['reference_001'])

    def response(self, body, result):
        return httpx.Response(200, json=dict(id='resp_knowledge_mock', model=body['model'], status='completed',
            output=[dict(type='message', id='msg_mock', role='assistant', status='completed',
                         content=[dict(type='output_text', text=json.dumps(result), annotations=[])])]))

    def test_fact_conflict_still_blocks_confirmation_after_knowledge_planning(self):
        def conflict(body, result):
            result['fact_issues'] = [self.issue()]
            return self.response(body, result)
        state = self.run_call(handler=conflict, knowledge_enabled=True, knowledge_conditions={'reference_001': self.k01()})
        self.assertEqual(self.post(state, 'confirm', 'reference_001').status_code, 409)
        self.assertFalse(state['confirmed'])

    def test_manual_edit_and_reconfirmation_do_not_change_call_evidence_or_adoption_status(self):
        state = self.run_call(knowledge_enabled=True, knowledge_conditions={'reference_001': self.k01()})
        folder = self.folder(state)
        original = {path: path.read_bytes() for path in folder.iterdir() if path.is_file()}
        self.assertFalse(state['confirmed'])
        plan = {**state['plans']['reference_001'], 'design': '人工重新安排结构，不是 Knowledge 效果认证。'}
        edited = self.post(state, 'manual_plan', 'reference_001', plan=plan,
                           plan_version=state['plan_versions']['reference_001'], knowledge_enabled=False)
        self.assertEqual(edited.status_code, 200, edited.json)
        state = edited.json['state']
        self.assertFalse(state['confirmed'])
        confirmed = self.post(state, 'confirm', 'reference_001', knowledge_enabled=False)
        self.assertEqual(confirmed.status_code, 200, confirmed.json)
        self.assertEqual(len(self.fx.requests), 1)
        self.assertEqual({path: path.read_bytes() for path in original}, original)
        self.assertEqual(json.loads((folder / 'knowledge.json').read_text())['model_adoption_status'], 'MODEL_ADOPTION_UNKNOWN')

    def test_free_operations_reject_enhancement_but_false_keeps_quality_compatibility(self):
        state = self.run_call()
        for action in ('confirm', 'manual_plan', 'resolve_conflict', 'set_quality'):
            self.assertEqual(self.post(state, action, 'reference_001', knowledge_enabled=True).status_code, 400)
        response = self.post(state, 'set_quality', knowledge_enabled=False,
                             quality_revision=state.get('quality_revision', 0), generation_quality='low')
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(len(self.fx.requests), 1)

    def test_reference_and_product_only_calls_record_no_design_methods(self):
        state = self.run_call()
        for kind, target in (('product', None), ('reference', 'reference_001')):
            state = self.run_call(state, kind, target, knowledge_enabled=True)
            knowledge, _, _ = self.evidence(state)
            self.assertEqual(knowledge['method_ids'], [])

    def test_historical_unclassified_task_is_not_silently_given_a_slot_type(self):
        state = self.run_call(self.create(classified=False), knowledge_enabled=True)
        knowledge, _, _ = self.evidence(state)
        self.assertEqual(knowledge['method_ids'], [])
        self.assertEqual({row['status'] for row in knowledge['selection_basis'].values()}, {'UNCLASSIFIED_REFERENCE'})

    def test_pure_projection_is_stable_and_does_not_mutate_task_or_original_assets(self):
        state = self.store.load(self.state['id'])
        before = copy.deepcopy(state)
        declarations = {'reference_002': self.k06(2), 'reference_001': self.k01()}
        original = copy.deepcopy(declarations)
        left = prepare_knowledge(state, 'understand', None, knowledge_conditions=declarations)
        right = prepare_knowledge(state, 'understand', None, knowledge_conditions=dict(reversed(list(declarations.items()))))
        self.assertEqual(left, right)
        self.assertEqual(state, before)
        self.assertEqual(declarations, original)


if __name__ == '__main__':
    unittest.main()
