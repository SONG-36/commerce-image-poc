"""E1-03 request policies: anonymous inputs, real SDK serialization, Mock transport.

Policy wire tests exercise the existing executor in isolation, so policies can
be verified while the public API gate remains closed. Public gate tests below
exercise the normal HTTP path; no test uses production data or real network.
"""

import copy
from email.parser import BytesParser
import json
import io
import unittest
from unittest.mock import patch
from uuid import uuid4

import httpx

import test_quick_v1 as cp1
from image_workflow.generation import auxiliary, quick_v1
from image_workflow.generation.request import build_generation_request, initial_context


class ScenarioFixture(unittest.TestCase):
    def setUp(self):
        self.fx = cp1.QuickV1Tests()
        self.fx.setUp()
        self.addCleanup(self.fx.doCleanups)
        self.client, self.store = self.fx.client, self.fx.store
        self.service = self.fx.fx.app.extensions['generation_service']

    def create(self, scenario, **extra):
        values = dict(quick_scenario=scenario, requirements='必须保留清晰适用的核心卖点；采用日语',
                      product_facts='运营补充资料，不是独立认证')
        response = self.fx.create(**{**values, **extra})
        self.assertEqual(response.status_code, 200, response.json)
        return self.store.load(response.json['state']['id'])

    def saved_request(self, state, target, record):
        folder = self.service.run_folder(state['id'], state['revision'], target, record['run_id'])
        evidence = json.loads((folder / 'request.json').read_text())
        context = json.loads((folder / 'plan.json').read_text())
        request = self.fx.fx.requests[-1]
        parts = BytesParser().parsebytes(('Content-Type: ' + request.headers['content-type'] + '\r\n\r\n').encode()
                                         + request.read()).get_payload()
        fields = {part.get_param('name', header='content-disposition'): part.get_payload(decode=True).decode()
                  for part in parts if not part.get_filename()}
        images = [part.get_payload(decode=True) for part in parts if part.get_filename()]
        self.assertEqual(fields['prompt'], evidence['prompt'])
        self.assertEqual((folder / 'prompt.txt').read_text(), fields['prompt'])
        self.assertEqual(fields['model'], 'gpt-image-2.5-sunburst')
        self.assertEqual((fields['quality'], fields['size'], fields['n']), ('low', '1024x1536', '1'))
        self.assertEqual(record['status'], 'SUCCEEDED')
        self.assertEqual((record['max_retries'], record['timeout_seconds']), (0, 180.0))
        self.assertEqual(context['quick_scenario'], state['quick_scenario'])
        self.assertEqual(evidence['quick_scenario'], state['quick_scenario'])
        return evidence, context, fields['prompt'], images


class PolicyWireTests(ScenarioFixture):
    def test_quick_a_actual_wire_permits_applicable_claims_and_preserves_visual_truth(self):
        state = self.create('quick_a')
        with self.fx.fx.with_sdk():
            record = self.service._generate(state, 'reference_101')
        evidence, context, prompt, images = self.saved_request(state, 'reference_101', record)
        self.assertIn('当前业务场景：quick_a', prompt)
        self.assertIn('运营声明目标商品与参考商品同款同外观', prompt)
        self.assertIn('保留适用的参考参数、功能和营销卖点', prompt)
        self.assertIn('不为差异化改变真实商品结构', prompt)
        self.assertIn('不得复制不适用的品牌、包装、配件或配置', prompt)
        self.assertIn('允许根据图位目标突出部分适用卖点', prompt)
        self.assertIn('运营明确必保留内容不得擅自删除', prompt)
        self.assertIn(state['inputs']['requirements'], prompt)
        self.assertIn(context['output_slot']['requirements'], prompt)
        self.assertEqual(images, self.fx.sources[:3] + [self.fx.references[0]])
        self.assertEqual([item['role'] for item in evidence['image_order']], ['product'] * 3 + ['design_reference'])
        self.assertNotIn('不得继承参考商品的结构、尺寸、品牌、功能或未经确认的比较宣称。', prompt)
        self.assertIn('不等于参考中所有文字可信', prompt)
        self.assertIn('最终成图必须由运营人工审核', prompt)

    def test_quick_b_actual_wire_replaces_all_subject_views_without_mixing_structure(self):
        state = self.create('quick_b')
        with self.fx.fx.with_sdk():
            record = self.service._generate(state, 'reference_103')
        evidence, context, prompt, images = self.saved_request(state, 'reference_103', record)
        self.assertIn('当前业务场景：quick_b', prompt)
        for phrase in ('参考中央主视觉、局部特写、结构展示、场景中的商品', '均必须替换为实际售卖商品',
                       '不得混合两款商品的外壳、按钮、接口、颜色或标识', '允许沿用经运营确认适用的参考营销信息',
                       '不自动继承参考商品专属品牌、包装、配件或不同配置', '按目标商品形态重新组织',
                       '不为匹配参考构图而扭曲实际商品外观', '本任务不是简单风格迁移',
                       '明显矛盾、不可辨识或明显不适用的信息不得猜测补全'):
            self.assertIn(phrase, prompt)
        self.assertEqual(images, self.fx.sources[:3] + [self.fx.references[2]])
        self.assertEqual(evidence['output_id'], 'reference_103')
        self.assertEqual(evidence['output_slot']['reference_id'], 'reference_003')
        self.assertEqual([item['id'] for item in evidence['image_order']], ['product_001', 'product_002', 'product_003', 'reference_003'])
        self.assertEqual(context['quick_scenario'], 'quick_b')

    def test_generation_and_edit_keep_scenario_primary_reference_parent_and_auxiliary_permissions(self):
        for scenario in quick_v1.SCENARIOS:
            state = self.create(scenario)
            helper = auxiliary.prepare_auxiliary('anonymous-style.png', self.fx.sources[1], 'design_style')
            with self.fx.fx.with_sdk():
                parent = self.service._generate(state, 'reference_101')
                first_folder = self.service.run_folder(state['id'], state['revision'], 'reference_101', parent['run_id'])
                original = {p.name: p.read_bytes() for p in first_folder.iterdir() if p.is_file()}
                edited = self.service._generate(state, 'reference_101', parent['run_id'], '只调整本图背景，必保留核心卖点', auxiliary=helper)
            evidence, context, prompt, images = self.saved_request(state, 'reference_101', edited)
            self.assertEqual(context['quick_scenario'], scenario)
            self.assertEqual(edited['parent_run_id'], parent['run_id'])
            self.assertEqual(context['parent_image']['run_id'], parent['run_id'])
            self.assertIn('只调整本图背景，必保留核心卖点', prompt)
            self.assertIn('允许按本场景业务前提沿用', prompt)
            self.assertIn('current_image 只是父 Run 的候选结果', prompt)
            self.assertIn('用途：设计风格参考', prompt)
            self.assertIn('该图只用于借鉴构图、排版、配色和风格', prompt)
            self.assertEqual([item['role'] for item in evidence['image_order']],
                             ['current_image', 'product', 'product', 'product', 'design_reference', 'auxiliary_reference'])
            self.assertEqual(images, [(first_folder / 'image.png').read_bytes()] + self.fx.sources[:3] +
                             [self.fx.references[0], helper['data']])
            self.assertEqual(original, {p.name: p.read_bytes() for p in first_folder.iterdir() if p.is_file()})
            if scenario == 'quick_b':
                self.assertIn('完整主体替换', prompt)
                self.assertIn('局部特写、结构展示、场景中的商品', prompt)

    def test_context_scene_mismatch_cannot_fall_back_to_legacy_or_another_scenario(self):
        state = self.create('quick_b')
        context = initial_context(state, 'reference_101', {'size': '1024x1536'})
        for scenario in (None, 'quick_a', 'unknown'):
            invalid = copy.deepcopy(context)
            if scenario is None:
                invalid.pop('quick_scenario')
            else:
                invalid['quick_scenario'] = scenario
            with self.assertRaisesRegex(ValueError, '场景不一致'):
                build_generation_request(state, invalid, [], [], 'offline-model', {}, '', '',
                                         editing=False, feedback='', auxiliary=None, prompts=None)


class ScenarioExecutionTests(ScenarioFixture):
    def test_uncategorized_quick_v1_actual_wire_keeps_historical_policy(self):
        state = self.fx.state
        with self.fx.fx.with_sdk():
            response = self.fx.generate(state=state)
        self.assertEqual(response.status_code, 200, response.json)
        folder = self.service.run_folder(state['id'], state['revision'], 'reference_101', response.json['run_id'])
        request = self.fx.fx.requests[-1]
        parts = BytesParser().parsebytes(('Content-Type: ' + request.headers['content-type'] + '\r\n\r\n').encode()
                                         + request.read()).get_payload()
        prompt = next(part.get_payload(decode=True).decode() for part in parts
                      if part.get_param('name', header='content-disposition') == 'prompt')
        self.assertIn('不得继承参考商品的结构、尺寸、品牌、功能或未经确认的比较宣称。', prompt)
        self.assertNotIn('当前业务场景：', prompt)
        for name in ('plan.json', 'request.json'):
            self.assertNotIn('quick_scenario', json.loads((folder / name).read_text()))
        self.assertNotIn('quick_scenario', self.store.load(state['id']))

    def test_http_all_non_dimension_types_use_scenario_policy_without_planning(self):
        configuration = cp1.slots()
        configuration[3].update(enabled=True, reference_id='reference_004')
        configuration.append(dict(id='reference_105', type='selling_point', enabled=True,
                                  reference_id='reference_005', requirements='必须保留本图适用卖点'))
        references = self.fx.references + [cp1.picture('cyan')]
        for scenario in quick_v1.SCENARIOS:
            state = self.create(scenario, configuration=configuration,
                reference=[(io.BytesIO(data), f'own-reference-{i}.png') for i, data in enumerate(references)])
            cards = self.fx.cards(state)
            self.assertEqual([card['id'] for card in cards if card['batch_eligible']],
                             ['reference_101', 'reference_103', 'reference_104', 'reference_105'])
            with self.fx.fx.with_sdk():
                for target in ('reference_101', 'reference_103', 'reference_104', 'reference_105'):
                    response = self.fx.generate(target, state=state)
                    self.assertEqual(response.status_code, 200, response.json)
                    folder = self.service.run_folder(state['id'], state['revision'], target, response.json['run_id'])
                    saved = json.loads((folder / 'request.json').read_text())
                    self.assertEqual(saved['quick_scenario'], scenario)
                    self.assertIn('当前业务场景：' + scenario, saved['prompt'])
                    self.assertEqual(saved['output_id'], target)
            self.assertFalse(any(card['passed_run'] for card in self.fx.cards(state)))
            self.assertFalse((self.store.folder(state['id']) / 'calls').exists())
        self.assertEqual(len(self.fx.fx.requests), 8)

    def test_http_revision_keeps_scenario_parent_pass_and_operation_dedup(self):
        for scenario in quick_v1.SCENARIOS:
            state = self.create(scenario)
            operation = uuid4().hex
            count = len(self.fx.fx.requests)
            with self.fx.fx.with_sdk():
                first = self.fx.generate(state=state, operation=operation)
                self.assertEqual(first.status_code, 200, first.json)
                parent = first.json['run_id']
                first_folder = self.service.run_folder(state['id'], state['revision'], 'reference_101', parent)
                before = {str(p.relative_to(first_folder)): p.read_bytes() for p in first_folder.rglob('*') if p.is_file()}
                replay = self.fx.generate(state=state, operation=operation)
                self.assertEqual(replay.json['run_id'], parent)
                self.assertEqual(len(self.fx.fx.requests), count + 1)
                card = self.fx.card(state=state)
                passed = self.client.post(f"/api/sessions/{state['id']}/review/reference_101", headers=cp1.fixtures.HEADERS,
                    json=dict(action='pass', run_id=parent, card_revision=card['card_revision'], confirmed_revision=state['revision']))
                self.assertEqual(passed.status_code, 200, passed.json)
                edited = self.fx.edit(parent=parent, state=state)
                self.assertEqual(edited.status_code, 200, edited.json)
            folder = self.service.run_folder(state['id'], state['revision'], 'reference_101', edited.json['run_id'])
            record = json.loads((folder / 'run.json').read_text())
            self.saved_request(state, 'reference_101', record)
            card = self.fx.card(state=state)
            self.assertEqual(card['passed_run'], parent)
            self.assertEqual(card['selected_run'], edited.json['run_id'])
            self.assertEqual(len(card['versions']), 2)
            self.assertEqual(record['parent_run_id'], parent)
            self.assertEqual(before, {str(p.relative_to(first_folder)): p.read_bytes() for p in first_folder.rglob('*') if p.is_file()})
            self.assertEqual(len(self.fx.fx.requests), count + 2)

    def test_dimensions_http_and_executor_guards_prevent_sdk_even_with_operator_claim(self):
        for scenario in quick_v1.SCENARIOS:
            state = self.create(scenario, product_facts='匿名夹具：运营声明已有尺寸标注；不能绕过尚未完成的专项校验')
            before = {str(p): p.read_bytes() for p in self.store.folder(state['id']).rglob('*') if p.is_file()}
            card = self.fx.card('reference_102', state)
            self.assertFalse(card['generation_allowed'])
            self.assertFalse(card['batch_eligible'])
            self.assertIn('E1-04', card['generation_block_reason'])
            with patch.object(cp1.fixtures.generation, 'make_client', side_effect=AssertionError('No SDK before E1-04')):
                response = self.fx.generate('reference_102', state=state)
                self.assertEqual(response.status_code, 409, response.json)
                self.assertIn('E1-04', response.json['error'])
                edited = self.fx.edit('reference_102', state=state, parent='20261028T000000Z-' + 'b' * 32)
                self.assertEqual(edited.status_code, 409, edited.json)
                self.assertIn('E1-04', edited.json['error'])
                self.assertEqual(before, {str(p): p.read_bytes() for p in self.store.folder(state['id']).rglob('*') if p.is_file()})
                # Defense at the pure request boundary also protects an executor caller.
                record = self.service._generate(state, 'reference_102')
                self.assertEqual(record['status'], 'FAILED')
                self.assertFalse(record['api_call_attempted'])
                self.assertIn('E1-04', record['error']['message'])
        self.assertEqual(self.fx.fx.requests, [])

    def test_new_scenario_api_failure_keeps_truthful_status_and_does_not_retry(self):
        state = self.create('quick_b')
        with self.fx.fx.with_sdk(lambda request: httpx.Response(429, json={'error': {'message': 'anonymous rate limit'}})):
            response = self.fx.generate(state=state)
        self.assertEqual(response.status_code, 502, response.json)
        self.assertEqual(len(self.fx.fx.requests), 1)
        card = self.fx.card(state=state)
        self.assertEqual(card['status'], 'FAILED')
        self.assertIsNone(card['passed_run'])
        self.assertIsNone(card['image_url'])
        folder = self.service.run_folder(state['id'], state['revision'], 'reference_101', response.json['run_id'])
        self.assertTrue((folder / 'error.json').is_file())
        self.assertEqual(json.loads((folder / 'request.json').read_text())['quick_scenario'], 'quick_b')

    def test_invalid_binding_or_scenario_never_opens_a_paid_path(self):
        before = set(self.store.root.rglob('*'))
        invalid = cp1.slots()
        invalid[0]['reference_id'] = 'product_001'
        self.assertEqual(self.fx.create(quick_scenario='quick_b', configuration=invalid).status_code, 400)
        self.assertEqual(self.fx.create(quick_scenario='unknown').status_code, 400)
        self.assertEqual(set(self.store.root.rglob('*')), before)
        state = self.create('quick_a')
        path = self.store.folder(state['id']) / 'state.json'
        saved = json.loads(path.read_text())
        saved['quick_slots'][0]['reference_id'] = 'other-task/reference_001'
        path.write_text(json.dumps(saved))
        response = self.client.post(f"/api/sessions/{state['id']}/generate/reference_101", headers=cp1.fixtures.HEADERS,
            json=dict(confirmed_revision=1, card_revision=0, operation_id=uuid4().hex))
        self.assertEqual(response.status_code, 409, response.json)
        self.assertEqual(self.fx.fx.requests, [])


if __name__ == '__main__':
    unittest.main()
