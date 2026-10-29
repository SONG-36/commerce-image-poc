"""F1/F2 contracts: anonymous temporary Evidence and actual SDK Mock serialization."""

import copy
from email.parser import BytesParser
import json
import unittest
from unittest.mock import patch

import app
from file_ops import sha256
from image_workflow.generation.request import initial_context
from image_workflow.inspector import InspectorError, InspectorReader, context_view
from image_workflow.inspector_graph import prompt_segments
import test_business_guards as guards
import test_generate_plan_image as images
import test_quick_v1 as quick


class ListingSlotContextTests(unittest.TestCase):
    def setUp(self):
        self.fx = guards.BusinessGuardTests()
        self.fx.setUp()
        self.addCleanup(self.fx.doCleanups)
        self.store, self.client = self.fx.store, self.fx.client
        self.service = self.fx.fx.app.extensions['generation_service']
        self.requirements = {'reference_001': 'OPERATOR_SELLING_ONLY：保留商品标签，不加徽章。',
                             'reference_002': 'OPERATOR_SCENE_ONLY：只用室内场景，不画水流。'}
        self.state = self.store.create(
            {'listing': '运营提供的商品文字，不是独立认证。', 'description': '同 SKU 商品资料。',
             'requirements': '整体使用日语。'},
            [('product', 'own.png', images.png((24, 32)))] +
            [('reference', f'ref-{i}.png', images.png((30 + i, 40))) for i in range(3)],
            'NEW ANONYMOUS F1 FIXTURE', listing_slots=[
                dict(id='reference_901', type='selling_point', enabled=True, reference_id='reference_001',
                     requirements=self.requirements['reference_001'], output_size='1024x1536'),
                dict(id='reference_902', type='scene', enabled=True, reference_id='reference_002',
                     requirements=self.requirements['reference_002'], output_size='1024x1536'),
                dict(id='reference_903', type='comparison', enabled=False, reference_id='reference_003',
                     requirements='DISABLED_REQUIREMENT_NOT_SENT', output_size='1024x1536')])
        self.state = self.fx.saved(self.fx.plan(self.state))

    def confirm(self, state, target):
        return self.fx.saved(self.fx.action(state, 'confirm', target))

    def evidence(self, state, target, response):
        self.assertEqual(response.status_code, 200, response.json)
        card = self.fx.card(state, target)
        folder = self.service.run_folder(state['id'], card['generation_revision'], target, response.json['run_id'])
        request = self.fx.fx.requests[-1]
        parts = BytesParser().parsebytes(('Content-Type: ' + request.headers['content-type'] + '\r\n\r\n').encode()
                                         + request.read()).get_payload()
        fields = {part.get_param('name', header='content-disposition'): part.get_payload(decode=True).decode()
                  for part in parts if not part.get_filename()}
        actual_images = [part.get_payload(decode=True) for part in parts if part.get_filename()]
        context = json.loads((folder / 'plan.json').read_text())
        saved = json.loads((folder / 'request.json').read_text())
        record = json.loads((folder / 'run.json').read_text())
        self.assertEqual(saved['prompt'], fields['prompt'])
        self.assertEqual((folder / 'prompt.txt').read_text(), fields['prompt'])
        self.assertEqual(record['prompt_sha256'], sha256(fields['prompt'].encode()))
        digest = sha256(json.dumps(context, ensure_ascii=False, sort_keys=True).encode())
        self.assertEqual((saved['context_sha256'], record['context_sha256']), (digest, digest))
        self.assertEqual([sha256(data) for data in actual_images], [item['sha256'] for item in saved['image_order']])
        for data, item in zip(actual_images, saved['image_order']):
            self.assertEqual((folder / item['file']).read_bytes(), data)
        self.assertEqual((context['reference_id'], record['reference_id']), (target, target))
        self.assertEqual(context['confirmed_revision'], card['generation_revision'])
        self.assertNotIn('id', context['output_slot'])  # UI Slot ID is not a Listing plan identity.
        self.assertEqual(context['output_slot']['reference_id'], target)
        self.assertIn('Operator Slot Requirements', fields['prompt'])
        self.assertIn('Confirmed Plan', fields['prompt'])
        return context, saved, record, fields, folder

    def generate(self, state, target, editing=False):
        with self.fx.fx.with_sdk():
            response = self.fx.generate(state, target, editing=editing)
        return self.evidence(state, target, response)

    def test_f1_01_selling_point_operator_requirements_are_independent_context(self):
        state = self.confirm(self.state, 'reference_001')
        context, _, _, fields, _ = self.generate(state, 'reference_001')
        self.assertEqual(context['output_slot']['type'], 'selling_point')
        self.assertEqual(context['output_slot']['requirements'], self.requirements['reference_001'])
        self.assertIn(self.requirements['reference_001'], fields['prompt'])
        self.assertEqual(context['confirmed_plan'], state['plans']['reference_001'])

    def test_f1_02_scene_requirements_reach_only_this_model_request(self):
        state = self.confirm(self.state, 'reference_002')
        context, saved, _, fields, _ = self.generate(state, 'reference_002')
        self.assertEqual(context['output_slot']['type'], 'scene')
        self.assertIn(self.requirements['reference_002'], fields['prompt'])
        self.assertNotIn(self.requirements['reference_001'], fields['prompt'])
        self.assertEqual([item['id'] for item in saved['image_order']], ['product_001', 'reference_002'])

    def test_f1_03_plan_omission_cannot_drop_original_operator_requirement(self):
        state = self.confirm(self.state, 'reference_001')
        self.assertNotIn(self.requirements['reference_001'], json.dumps(state['plans'], ensure_ascii=False))
        context, _, _, fields, _ = self.generate(state, 'reference_001')
        self.assertIn(self.requirements['reference_001'], fields['prompt'])
        self.assertNotIn(self.requirements['reference_001'], json.dumps(context['confirmed_plan'], ensure_ascii=False))
        self.assertIn('不能覆盖商品事实权限', fields['prompt'])

    def test_f1_04_manual_edit_keeps_original_requirements_and_needs_reconfirmation(self):
        state = self.confirm(self.state, 'reference_001')
        originals = {p: p.read_bytes() for p in self.store.folder(state['id']).glob('calls/**/*') if p.is_file()}
        plan = {**state['plans']['reference_001'], 'design': 'HUMAN_EDIT_LAYOUT_WITHOUT_REPEATING_REQUIREMENT'}
        with patch('app.call_ai', side_effect=AssertionError('Manual edit must be free')):
            state = self.fx.saved(self.fx.action(state, 'manual_plan', 'reference_001',
                plan=plan, plan_version=state['plan_versions']['reference_001']))
        self.assertEqual(self.fx.generate(state, 'reference_001').status_code, 409)
        state = self.confirm(state, 'reference_001')
        context, _, record, fields, _ = self.generate(state, 'reference_001')
        self.assertEqual(context['confirmed_plan'], plan)
        self.assertEqual(record['plan_version'], state['plan_versions']['reference_001'])
        self.assertIn(plan['design'], fields['prompt'])
        self.assertIn(self.requirements['reference_001'], fields['prompt'])
        self.assertEqual({p: p.read_bytes() for p in originals}, originals)

    def test_f1_05_revision_keeps_slot_parent_and_current_feedback(self):
        state = self.confirm(self.state, 'reference_002')
        _, _, first, _, folder = self.generate(state, 'reference_002')
        original = {p: p.read_bytes() for p in folder.rglob('*') if p.is_file()}
        context, saved, record, fields, _ = self.generate(state, 'reference_002', editing=True)
        self.assertEqual(record['parent_run_id'], first['run_id'])
        self.assertEqual(context['operator_feedback'], '仅调整背景')
        self.assertEqual(context['output_slot']['requirements'], self.requirements['reference_002'])
        self.assertIn(self.requirements['reference_002'], fields['prompt'])
        self.assertIn('仅调整背景', fields['prompt'])
        self.assertEqual([item['role'] for item in saved['image_order']], ['current_image', 'product', 'reference'])
        self.assertEqual({p: p.read_bytes() for p in original}, original)

    def test_f1_06_multiple_slots_do_not_mix_requirements_or_references(self):
        state = self.confirm(self.confirm(self.state, 'reference_001'), 'reference_002')
        for target in self.requirements:
            context, saved, _, fields, _ = self.generate(state, target)
            for other, text in self.requirements.items():
                self.assertEqual(text in fields['prompt'], other == target)
            self.assertNotIn('DISABLED_REQUIREMENT_NOT_SENT', fields['prompt'])
            self.assertEqual([i['id'] for i in saved['image_order'] if i['role'] == 'reference'], [target])
            self.assertEqual(context['output_slot']['reference_id'], target)

    def test_f1_07_uses_confirmed_snapshot_not_later_other_plan_revision(self):
        state = self.confirm(self.state, 'reference_001')
        revision = self.store.image_state(state, 'reference_001')['revision']
        state = self.confirm(state, 'reference_002')
        context, _, record, _, _ = self.generate(state, 'reference_001')
        self.assertLess(revision, state['revision'])
        self.assertEqual((context['confirmed_revision'], record['confirmed_revision']), (revision, revision))
        snapshot = self.store.read_snapshot(state['id'], revision)
        self.assertEqual(context['confirmed_plan'], snapshot['plans']['reference_001'])
        self.assertEqual(context['output_slot']['requirements'], snapshot['listing_slots'][0]['requirements'])
        calls = len(self.fx.fx.requests)
        response = self.client.post(f"/api/sessions/{state['id']}/generate/reference_001", headers=images.HEADERS,
                                    json={'confirmed_revision': state['revision']})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(len(self.fx.fx.requests), calls)

    def test_f1_08_dimensions_and_fact_conflicts_still_block_before_sdk(self):
        state = self.fx.saved(self.fx.create('listing', source=None, declared=False))
        state = self.fx.saved(self.fx.plan(state))
        state = self.confirm(state, 'reference_001')
        before = self.fx.files(state)
        self.assertEqual(self.fx.generate(state, 'reference_001').status_code, 409)
        self.assertEqual(self.fx.files(state), before)
        report = self.fx.report(target='reference_002')
        report['text_evidence'] = {'source': 'listing', 'quote': self.state['inputs']['listing']}
        disputed = self.fx.saved(self.fx.plan(self.state, [report],
            action='plan', target='reference_002', feedback='匿名修订'))
        self.assertEqual(self.fx.action(disputed, 'confirm', 'reference_002').status_code, 409)
        self.assertEqual(self.fx.generate(disputed, 'reference_002').status_code, 409)
        self.assertEqual(self.fx.fx.requests, [])

    def test_f1_09_unclassified_history_stays_blocked_without_rewrite(self):
        state = self.store.create(self.state['inputs'],
            [('product', 'old-own.png', images.png()), ('reference', 'old-ref.png', images.png())], 'anonymous old task')
        state = self.fx.saved(self.fx.plan(state))
        state = self.confirm(state, 'reference_001')
        before = self.fx.files(state)
        self.assertEqual(self.fx.generate(state, 'reference_001').status_code, 409)
        self.assertEqual(self.fx.files(state), before)
        self.assertNotIn('output_slot', initial_context(state, 'reference_001', {'size': '1024x1536'}))
        self.assertEqual(self.fx.fx.requests, [])

    def test_f1_10_wire_prompt_context_inputs_and_request_are_consistent(self):
        state = self.confirm(self.state, 'reference_001')
        for editing in (False, True):
            context, saved, record, fields, _ = self.generate(state, 'reference_001', editing=editing)
            for key in ('model', 'n', 'quality', 'size', 'output_format'):
                self.assertEqual(fields[key], str(saved[key]))
            self.assertEqual((record['max_retries'], record['timeout_seconds']), (0, 180.0))
            if not editing:
                sent = fields['prompt'].split('<confirmed_image_context>\n')[1].split('\n</confirmed_image_context>')[0]
                self.assertEqual(json.loads(sent), context)


class QuickPromptParsingTests(unittest.TestCase):
    def setUp(self):
        self.fx = quick.QuickV1Tests()
        self.fx.setUp()
        self.addCleanup(self.fx.doCleanups)

    def saved_run(self, scenario=None, *, editing=False, **extra):
        rows = quick.slots()
        rows[2]['requirements'] = 'CURRENT_SLOT_REQUIREMENT_ONLY'
        values = {'configuration': rows, 'requirements': 'GLOBAL_REQUIREMENTS_ONLY',
                  'product_facts': 'PRODUCT_FACTS_ONLY', **extra}
        if scenario:
            values['quick_scenario'] = scenario
        state = self.fx.create(**values).json['state']
        with self.fx.fx.with_sdk():
            response = self.fx.generate('reference_103', state=state)
            self.assertEqual(response.status_code, 200, response.json)
            if editing:
                response = self.fx.edit('reference_103', state=state, parent=response.json['run_id'])
        self.assertEqual(response.status_code, 200, response.json)
        service = self.fx.fx.app.extensions['generation_service']
        folder = service.run_folder(state['id'], state['revision'], 'reference_103', response.json['run_id'])
        reader = InspectorReader(self.fx.fx.runtime, [state['id']])
        return state, folder, reader, response.json['run_id']

    def view(self, state, reader, run):
        return reader.inspect(state['id'], 'reference_103', state['revision'], run)

    def assert_sections(self, state, folder, reader, run):
        before = {p: p.read_bytes() for p in folder.rglob('*') if p.is_file()}
        view = self.view(state, reader, run)
        prompt = json.loads((folder / 'request.json').read_text())['prompt']
        expected = {'operator_design_requirements': state['inputs']['requirements'],
                    'product_constraints_from_operator': state['inputs']['product_facts'],
                    'slot_requirements': 'CURRENT_SLOT_REQUIREMENT_ONLY',
                    'revision_feedback': json.loads((folder / 'run.json').read_text())['feedback']}
        for tag, text in expected.items():
            matches = prompt_segments(prompt, tag, quick_v1=True)
            self.assertEqual(len(matches), 1, tag)
            self.assertEqual(matches[0].group(1), text)
            self.assertEqual(prompt[matches[0].start(1):matches[0].end(1)], text)
        cards = {card['id']: card for card in view['context_view']['cards']}
        self.assertEqual([c['result'] for c in cards['assembly']['checks'][:2]], ['MATCH', 'MATCH'])
        if expected['revision_feedback']:
            self.assertEqual(cards['assembly']['checks'][2]['result'], 'MATCH')
        for key in ('E11', 'E12'):
            edge = next(e for e in view['graph_view']['edges'] if e['key'] == key)
            self.assertEqual(edge['evidence_status'], 'OBSERVED')
            self.assertIn('text_span', edge['evidence_refs'][-1])
        self.assertEqual({p: p.read_bytes() for p in before}, before)
        return view

    def test_f2_01_historical_v1_fact_title_is_parsed(self):
        state, folder, reader, run = self.saved_run()
        self.assertIn('\n商品事实说明：\n', (folder / 'prompt.txt').read_text())
        self.assert_sections(state, folder, reader, run)

    def test_f2_02_quick_a_exact_new_title_is_parsed(self):
        for editing in (False, True):
            self.assert_sections(*self.saved_run('quick_a', editing=editing))

    def test_f2_03_quick_b_exact_new_title_is_parsed(self):
        for editing in (False, True):
            self.assert_sections(*self.saved_run('quick_b', editing=editing))

    def test_f2_04_section_boundaries_preserve_multiline_content_and_inline_words(self):
        state, folder, reader, run = self.saved_run('quick_a', **{
            'requirements': '整体第一行\n商品事实说明：这是一段普通文案，不是独立标题。\n整体末行',
            'product_facts': '商品第一行\n运营补充商品资料（来源陈述，非独立认证）：这也只是行内文案。\n商品末行'})
        self.assert_sections(state, folder, reader, run)

    def test_f2_05_slot_section_matches_only_current_bound_slot(self):
        for scenario in (None, 'quick_a', 'quick_b'):
            view = self.assert_sections(*self.saved_run(scenario))
            fields = next(card for card in view['context_view']['cards'] if card['id'] == 'requirements')['fields']
            self.assertEqual([field['value'] for field in fields[3:]],
                             ['scene', 'reference_003', 'CURRENT_SLOT_REQUIREMENT_ONLY'])

    def test_f2_06_missing_unknown_duplicate_or_reordered_headings_stay_unknown(self):
        state, folder, reader, run = self.saved_run('quick_b')
        original = self.view(state, reader, run)
        prompt = (folder / 'prompt.txt').read_text()
        new = '运营补充商品资料（来源陈述，非独立认证）：'
        variants = [prompt.replace(new, '来源资料：'), prompt.replace(new, new + '（近似标题）'),
                    prompt.replace(new, new + '\n商品事实说明：'),
                    prompt.replace(new, new + '\n' + new),
                    prompt.replace('整体要求：', '本图可选补充要求：', 1)]
        for value in variants:
            nodes = copy.deepcopy(original['nodes'])
            generation = next(node for node in nodes if node['id'] == 'generation')
            next(doc for doc in generation['documents'] if doc['key'] == 'request.json')['data']['prompt'] = value
            projected = context_view(original['selection'], 'quick_redesign', nodes, original['assets'])
            checks = next(card for card in projected['cards'] if card['id'] == 'assembly')['checks']
            self.assertEqual([check['result'] for check in checks[:2]], ['UNKNOWN', 'UNKNOWN'])
            self.assertEqual(prompt_segments(value, 'slot_requirements', quick_v1=True), [])

    def test_f2_07_inspection_keeps_saved_prompt_hash_and_all_evidence_unchanged(self):
        state, folder, reader, run = self.saved_run('quick_a')
        task = self.fx.store.folder(state['id'])
        before = {p: sha256(p.read_bytes()) for p in task.rglob('*') if p.is_file()}
        for _ in range(2):
            self.assert_sections(state, folder, reader, run)
        record = json.loads((folder / 'run.json').read_text())
        self.assertEqual(record['prompt_sha256'], sha256((folder / 'prompt.txt').read_bytes()))
        self.assertEqual({p: sha256(p.read_bytes()) for p in before}, before)

    def test_f2_08_read_only_scope_paths_and_redaction_are_preserved(self):
        state, folder, reader, run = self.saved_run('quick_b')
        with self.assertRaises(InspectorError):
            reader.inspect('f' * 32)
        with self.assertRaises(InspectorError):
            reader.asset(state['id'], 'reference_103', state['revision'], run, '../../outside')
        secret = 'sk-offline-context-contract-canary-1234567890'
        from image_workflow.inspector import preview
        self.assertNotIn(secret, json.dumps(preview({'authorization': secret, 'text': secret})))
        application = app.create_local_debug_app(self.fx.fx.runtime, [state['id']], execution_mode='MOCK')
        client = application.test_client()
        self.assertEqual(client.post(f"/api/inspector/tasks/{state['id']}", headers=images.HEADERS).status_code, 405)
        self.assertEqual(client.get(f"/api/inspector/tasks/{state['id']}", headers={'Host': 'outside.example'}).status_code, 404)
        self.assertEqual(client.get(f"/api/inspector/tasks/{state['id']}", headers={'Origin': 'https://outside.example'}).status_code, 404)
