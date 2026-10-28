"""E1-02 dynamic N: temporary anonymous inputs and SDK Mock, never real AI."""

import base64
import copy
from email.parser import BytesParser
import io
import json
import unittest
from unittest.mock import patch
from uuid import uuid4
import zipfile

import httpx
import test_generate_plan_image as generation_fixture
import test_prepare_plan as planning_fixture
from image_workflow.generation import quick_v1


SIZES = ('1024x1024', '1024x1536', '1536x1024')


def rows(selling=4, scenes=3):
    kinds = ['main', 'dimensions', 'comparison'] + ['selling_point'] * selling + ['scene'] * scenes
    return [dict(id=f'reference_{201+i}', type=kind, enabled=True,
                 reference_id=f'reference_{len(kinds)-i:03}', requirements=f'匿名图位 {i} 的补充要求',
                 output_size=SIZES[i % len(SIZES)]) for i, kind in enumerate(kinds)]


class DynamicSlotTests(unittest.TestCase):
    def setUp(self):
        self.fx = generation_fixture.GenerationPageTests()
        self.fx.setUp()
        self.addCleanup(self.fx.doCleanups)
        self.client, self.store = self.fx.client, self.fx.store
        self.enterContext(patch('socket.socket.connect', side_effect=AssertionError('No network')))
        self.enterContext(patch.object(generation_fixture.web, 'OpenAI', side_effect=AssertionError('No real Planning')))
        self.wire = []

    def create(self, mode='quick_a', configuration=None):
        configuration = rows() if configuration is None else configuration
        data = dict(title='Anonymous dynamic N', mode='product_pack' if mode == 'listing' else 'quick_redesign',
                    listing='运营提供资料，未经独立核实', description='匿名商品资料', requirements='统一任务要求',
                    product=[(io.BytesIO(generation_fixture.png((24+i, 32))), f'product-{i}.png') for i in range(3)],
                    # One extra unbound reference must never leak into model inputs.
                    reference=[(io.BytesIO(generation_fixture.png((32, 40+i))), f'ref-{i}.png')
                               for i in range(len(configuration)+1)])
        if mode == 'listing':
            configuration = copy.deepcopy(configuration)
            for slot in configuration:
                if slot['type'] == 'dimensions':
                    slot.update(dimension_source_product_id='product_002', dimension_source_confirmed=True)
            data['listing_slots'] = json.dumps(configuration)
        else:
            data.update(quick_business_version='v1',
                quick_slots=json.dumps([{k: v for k, v in row.items() if k != 'output_size'} for row in configuration]),
                image_sizes=json.dumps({row['id']: row['output_size'] for row in configuration}))
            if mode != 'legacy_v1':
                data['quick_scenario'] = mode
        return self.client.post('/api/sessions', headers=generation_fixture.HEADERS, data=data)

    def state(self, response):
        self.assertEqual(response.status_code, 200, response.json)
        return response.json['state']

    def cards(self, state, client=None):
        response = (client or self.client).get(f"/api/sessions/{state['id']}/generation")
        self.assertEqual(response.status_code, 200, response.json)
        return response.json['cards']

    def action(self, state, action, target=None, **extra):
        return self.client.post(f"/api/sessions/{state['id']}/action", headers=generation_fixture.HEADERS,
            json=dict(action=action, revision=state['revision'], target=target, feedback='', **extra))

    def planned(self):
        state = self.state(self.create('listing'))
        helper = planning_fixture.PreparePlanTests()
        helper.requests = []
        with helper.with_ai():
            state = self.state(self.action(state, 'understand'))
        return state, helper

    def confirm(self, state, target):
        return self.state(self.action(state, 'confirm', target,
            plan_version=state['plan_status'][target]['plan_version']))

    def files(self, state):
        return {p.relative_to(self.store.folder(state['id'])).as_posix(): p.read_bytes()
                for p in self.store.folder(state['id']).rglob('*') if p.is_file()}

    def test_more_than_eight_enabled_outputs_and_larger_samples_restore_without_truncation(self):
        for mode in ('quick_a', 'quick_b', 'listing', 'legacy_v1'):
            with self.subTest(mode=mode):
                state = self.state(self.create(mode))
                key = 'listing_slots' if mode == 'listing' else 'quick_slots'
                saved = state[key]
                self.assertEqual(len(saved), 10)
                self.assertEqual(sum(row['type'] == 'selling_point' for row in saved), 4)
                self.assertEqual(sum(row['type'] == 'scene' for row in saved), 3)
                self.assertTrue(all(row['enabled'] for row in saved))
                self.assertEqual(self.store.load(state['id'])[key], saved)
                self.assertEqual(self.client.get('/api/sessions/' + state['id']).json['state'][key], saved)
                expected = [row['reference_id'] if mode == 'listing' else row['id'] for row in saved]
                self.assertEqual([card['id'] for card in self.cards(state)], expected)
        # These counts are samples rather than substitute fixed upper bounds.
        for mode in ('quick_a', 'listing'):
            state = self.state(self.create(mode, rows(12, 9)))
            self.assertEqual(len(self.cards(state)), 24)

    def test_invalid_ids_references_types_sizes_and_singletons_still_rejected_above_eight(self):
        invalid = []
        for kind in ('main', 'dimensions', 'comparison'):
            config = rows()
            config[3]['type'] = kind
            invalid.append(config)
        for key, value in (('id', 'reference_201'), ('id', '../reference_202'), ('reference_id', 'product_001'),
                           ('reference_id', 'reference_999'), ('reference_id', 'a'*32+'/reference_001'),
                           ('reference_id', 'reference_010'), ('enabled', 'true'), ('type', 'video'),
                           ('requirements', 'x' * 12001), ('output_size', '100x100'), ('path', '/etc/passwd')):
            config = rows()
            config[4][key] = value
            invalid.append(config)
        for mode in ('quick_a', 'listing'):
            before = set(self.store.root.rglob('*'))
            for config in invalid:
                with self.subTest(mode=mode, row=config[4]):
                    self.assertEqual(self.create(mode, config).status_code, 400)
            self.assertEqual(set(self.store.root.rglob('*')), before)

    def test_save_as_preserves_order_sizes_and_remapped_reference_bytes_without_changing_original(self):
        for mode in ('quick_a', 'quick_b', 'listing', 'legacy_v1'):
            state = self.state(self.create(mode))
            key = 'listing_slots' if mode == 'listing' else 'quick_slots'
            before = self.files(state)
            config = copy.deepcopy(state[key])
            removed = config.pop(4)
            references = [image for image in state['images'] if image['role'] == 'reference' and
                          image['id'] in {row['reference_id'] for row in config}]
            remap = {image['id']: f'reference_{i+1:03}' for i, image in enumerate(references)}
            for row in config:
                row['reference_id'] = remap[row['reference_id']]
            kept = [image for image in state['images'] if image['role'] == 'product'] + references
            form = dict(title='Anonymous dynamic copy', mode=state['mode'], from_session=state['id'],
                        keep_images=json.dumps([image['id'] for image in kept]), **state['inputs'])
            form[key] = json.dumps(config)
            if mode != 'listing':
                form['quick_business_version'] = 'v1'
                form['image_sizes'] = json.dumps({row['id']: state['image_sizes'][row['id']] for row in config})
            if 'quick_scenario' in state:
                form['quick_scenario'] = state['quick_scenario']
            clone = self.state(self.client.post('/api/sessions', headers=generation_fixture.HEADERS, data=form))
            self.assertEqual([row['id'] for row in clone[key]], [row['id'] for row in config])
            self.assertNotIn(removed['id'], [row['id'] for row in clone[key]])
            self.assertEqual(clone[key], config)
            for old in references:
                new = next(image for image in clone['images'] if image['id'] == remap[old['id']])
                self.assertEqual(new['sha256'], old['sha256'])
                self.assertEqual(self.store.read_input(clone['id'], new['file']), self.store.read_input(state['id'], old['file']))
            self.assertEqual(self.files(state), before)
            restarted = generation_fixture.web.create_app(self.fx.runtime).test_client()
            self.assertEqual(restarted.get('/api/sessions/' + clone['id']).json['state'][key], config)
            self.assertEqual(len(self.cards(clone, restarted)), 9)

    def test_new_quick_dimensions_remain_blocked_even_after_former_eighth_output(self):
        for mode in ('quick_a', 'quick_b'):
            config = rows()
            config[1]['type'], config[-1]['type'] = config[-1]['type'], 'dimensions'
            state = self.state(self.create(mode, config))
            before = self.files(state)
            for card in self.cards(state):
                self.assertEqual(card['generation_allowed'], card['id'] != 'reference_210')
                self.assertEqual(card['batch_eligible'], card['id'] != 'reference_210')
            for target in ('reference_210',):
                for verb in ('generate', 'revise'):
                    response = self.client.post(f"/api/sessions/{state['id']}/{verb}/{target}",
                        headers=generation_fixture.HEADERS, json=dict(confirmed_revision=1, card_revision=0,
                            operation_id=uuid4().hex, parent_run_id='20261028T000000Z-'+'a'*32, feedback='仅改背景'))
                    self.assertEqual(response.status_code, 409, response.json)
                    self.assertIn('尺寸', response.json['error'])
                    self.assertIn('未调用模型', response.json['error'])
            self.assertEqual(self.files(state), before)
        self.assertEqual(self.fx.requests, [])

    def test_listing_planning_maps_all_rows_and_confirms_only_the_selected_reference(self):
        state, helper = self.planned()
        content = helper.requests[0]['input'][0]['content']
        context = json.loads(content[0]['text'])
        expected = {row['reference_id']: row for row in state['listing_slots']}
        self.assertEqual(context['output_slot_inputs'], expected)
        self.assertEqual(context['required_reference_ids'], list(expected))
        self.assertEqual(set(state['plans']), set(expected))
        self.assertFalse(set(state['plans']) & {row['id'] for row in rows()})
        self.assertEqual(len([item for item in content if item['type'] == 'input_image']), 13)
        self.assertFalse(any(item.get('text', '').startswith('reference_011：') for item in content))
        target = rows()[-1]['reference_id']
        state = self.confirm(state, target)
        confirmed = [key for key, status in state['plan_status'].items() if status['confirmed']]
        self.assertEqual(confirmed, [target])
        snapshot = self.store.image_state(self.store.load(state['id']), target)
        self.assertEqual(snapshot['plans'][target], state['plans'][target])
        self.assertEqual(len(helper.requests), 1)

    def test_partial_or_incomplete_planning_preserves_old_plans_confirmations_and_failure_evidence(self):
        for failure in ('missing_plan', 'incomplete_response'):
            state, helper = self.planned()
            state = self.confirm(state, rows()[-1]['reference_id'])
            before = self.files(state)
            def response(body, result):
                result['plans'].pop(rows()[-1]['reference_id'])
                return httpx.Response(200, json=dict(id='resp_offline_partial', object='response', model=body['model'],
                    status='incomplete' if failure == 'incomplete_response' else 'completed',
                    output=[dict(type='message', id='msg_offline', role='assistant', status='completed',
                                 content=[dict(type='output_text', text=json.dumps(result), annotations=[])])]))
            with helper.with_ai(response):
                rejected = self.action(state, 'replan')
            self.assertEqual(rejected.status_code, 502, rejected.json)
            restored = self.store.load(state['id'])
            self.assertEqual(restored['revision'], state['revision'])
            self.assertEqual(restored['plans'], state['plans'])
            self.assertEqual(restored['plan_confirmations'], state['plan_confirmations'])
            for path, data in before.items():
                self.assertEqual((self.store.folder(state['id']) / path).read_bytes(), data)
            calls = list((self.store.folder(state['id']) / 'calls').iterdir())
            self.assertEqual(len(calls), 2)
            failed = next(folder for folder in calls if json.loads((folder / 'run.json').read_text())['status'] == 'FAILED')
            for name in ('request.json', 'response.json', 'error.json'):
                self.assertTrue((failed / name).is_file())
            self.assertFalse((failed / 'applied.json').exists())
            self.assertEqual(len(helper.requests), 2)  # One initial request, one explicit failed replan; no retry.

    def respond(self, request):
        message = BytesParser().parsebytes(('Content-Type: '+request.headers['content-type']+'\r\n\r\n').encode()+request.read())
        parts = message.get_payload()
        fields = {part.get_param('name', header='content-disposition'): part.get_payload(decode=True).decode()
                  for part in parts if not part.get_filename()}
        self.wire.append(dict(fields=fields, images=[part.get_payload(decode=True) for part in parts if part.get_filename()]))
        size = tuple(map(int, fields['size'].split('x')))
        image = io.BytesIO()
        generation_fixture.Image.new('RGB', size, (len(self.wire), 36, 72)).save(image, 'PNG')
        return httpx.Response(200, json={'data': [{'b64_json': base64.b64encode(image.getvalue()).decode()}]})

    def test_ten_listing_outputs_sizes_versions_pass_and_both_zips_without_executor_changes(self):
        state, _ = self.planned()
        for row in rows():
            state = self.confirm(state, row['reference_id'])
        originals = {}
        service = self.fx.app.extensions['generation_service']
        def submit(target, edit=False, **extra):
            card = next(card for card in self.cards(state) if card['id'] == target)
            body = dict(confirmed_revision=card['generation_revision'], card_revision=card['card_revision'], operation_id=uuid4().hex)
            if edit:
                body.update(parent_run_id=card['selected_run'], feedback='只调整本图背景')
            body.update(extra)
            response = self.client.post(f"/api/sessions/{state['id']}/{'revise' if edit else 'generate'}/{target}",
                                        headers=generation_fixture.HEADERS, json=body)
            return response, body
        def review(target, action, run):
            card = next(card for card in self.cards(state) if card['id'] == target)
            response = self.client.post(f"/api/sessions/{state['id']}/review/{target}", headers=generation_fixture.HEADERS,
                json=dict(action=action, run_id=run, confirmed_revision=card['generation_revision'], card_revision=card['card_revision']))
            self.assertEqual(response.status_code, 200, response.json)
        with self.fx.with_sdk(self.respond):
            for i, row in enumerate(rows()):
                target = row['reference_id']
                response, body = submit(target, batch_only=True)
                self.assertEqual(response.status_code, 200, response.json)
                run_id = response.json['run_id']
                folder = service.run_folder(state['id'], response.json['confirmed_revision'], target, run_id)
                saved = json.loads((folder / 'request.json').read_text())
                self.assertEqual(saved['size'], row['output_size'])
                self.assertEqual(self.wire[-1]['fields']['size'], row['output_size'])
                self.assertEqual([image['id'] for image in saved['image_order']], ['product_001', 'product_002', 'product_003', target])
                expected = [self.store.read_input(state['id'], image['file']) for image in state['images']
                            if image['role'] == 'product' or image['id'] == target]
                self.assertEqual(self.wire[-1]['images'], expected)
                plan = json.loads((folder / 'plan.json').read_text())
                self.assertEqual(plan['confirmed_plan'], state['plans'][target])
                originals[target] = (run_id, (folder / 'image.png').read_bytes())
                if i == 0:
                    duplicate = self.client.post(f"/api/sessions/{state['id']}/generate/{target}", headers=generation_fixture.HEADERS, json=body)
                    self.assertEqual(duplicate.status_code, 409)  # Existing batch eligibility rejects a second batch submission.
                    self.assertEqual(len(self.wire), 1)
                    replay = self.client.post(f"/api/sessions/{state['id']}/generate/{target}", headers=generation_fixture.HEADERS,
                                              json={**body, 'batch_only': False})
                    self.assertEqual(replay.status_code, 200, replay.json)
                    self.assertEqual(replay.json['run_id'], run_id)
                    self.assertEqual(len(self.wire), 1)
                review(target, 'pass', run_id)
            target = rows()[4]['reference_id']
            edited, _ = submit(target, edit=True)
            self.assertEqual(edited.status_code, 200, edited.json)
            card = next(card for card in self.cards(state) if card['id'] == target)
            self.assertEqual(card['passed_run'], originals[target][0])
            self.assertEqual(card['selected_run'], edited.json['run_id'])
            self.assertEqual(len(card['versions']), 2)
            folder = service.run_folder(state['id'], edited.json['confirmed_revision'], target, edited.json['run_id'])
            self.assertEqual(json.loads((folder / 'run.json').read_text())['parent_run_id'], originals[target][0])
            self.assertEqual(json.loads((folder / 'request.json').read_text())['size'], rows()[4]['output_size'])
            review(target, 'select', originals[target][0])
        self.assertEqual(len(self.wire), 11)
        with self.fx.with_sdk(lambda request: httpx.Response(429, json={'error': {'message': 'offline rate limit'}})):
            failed, _ = submit(rows()[-1]['reference_id'])
        self.assertEqual(failed.status_code, 502)
        self.assertEqual(len(self.fx.requests), 12)  # No automatic retry after the 429.
        last = self.cards(state)[-1]
        self.assertEqual(last['status'], 'FAILED')
        self.assertEqual(last['passed_run'], originals[last['id']][0])
        self.assertEqual(last['selected_run'], originals[last['id']][0])
        final = self.client.post(f"/api/sessions/{state['id']}/export-passed", headers=generation_fixture.HEADERS)
        self.assertEqual(final.status_code, 200)
        with zipfile.ZipFile(io.BytesIO(final.data)) as archive:
            expected_names = [f'图片_{i+1:02}_V1.png' for i in range(10)]
            self.assertEqual(archive.namelist(), expected_names)
            self.assertEqual(len(set(archive.namelist())), 10)
            self.assertEqual([archive.read(name) for name in expected_names], [originals[row['reference_id']][1] for row in rows()])
        package = self.client.post(f"/api/sessions/{state['id']}/export-experiment", headers=generation_fixture.HEADERS)
        self.assertEqual(package.status_code, 200, package.json)
        with zipfile.ZipFile(io.BytesIO(package.data)) as archive:
            self.assertEqual(len(archive.namelist()), len(set(archive.namelist())))
            requests = [name for name in archive.namelist() if '/runs/' in name and name.endswith('/request.json')]
            self.assertEqual(len(requests), 12)
        restarted = generation_fixture.web.create_app(self.fx.runtime).test_client()
        self.assertEqual([card['passed_run'] for card in self.cards(state, restarted)], [originals[row['reference_id']][0] for row in rows()])


if __name__ == '__main__':
    unittest.main()
