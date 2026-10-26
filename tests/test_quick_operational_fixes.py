"""Dynamic-upload contracts and per-output Images parameters; anonymous SDK Mock."""

import base64
from email.parser import BytesParser
import io
import json
import unittest
from unittest.mock import patch
from uuid import uuid4
import zipfile

import httpx

import app
import test_generate_plan_image as fixtures
import test_prepare_plan as planning_fixtures
import test_quick_v1 as cp1


class OutputSizeTests(unittest.TestCase):
    def setUp(self):
        self.fx = fixtures.GenerationPageTests()
        self.fx.setUp()
        self.addCleanup(self.fx.doCleanups)
        self.client, self.store = self.fx.client, self.fx.store
        self.enterContext(patch('socket.socket.connect', side_effect=AssertionError('No network')))
        self.sizes = ['1024x1024', '1024x1536', '1536x1024']
        self.wire = []

    def create(self, mode='quick_redesign', sizes=None, **extra):
        data = {'mode': mode, 'title': 'Anonymous per-output sizes', 'listing': 'Source statement, unverified',
                'description': 'Anonymous product', 'requirements': 'Keep product identity',
                'output_size': '1536x1024',
                'product': [(io.BytesIO(cp1.picture(color)), name + '.png') for color, name in
                            [('white', 'white'), ('blue', 'dimensions'), ('green', 'detail')]],
                'reference': [(io.BytesIO(cp1.picture(color)), 'ref-' + color + '.png') for color in ('red', 'orange', 'purple')]}
        if mode == 'quick_redesign':
            data.update(quick_business_version='v1', quick_slots=json.dumps(cp1.slots()))
        if sizes is not None:
            data['image_sizes'] = json.dumps(sizes)
        data.update(extra)
        return self.client.post('/api/sessions', headers=fixtures.HEADERS, data=data)

    def card(self, state, target):
        result = self.client.get('/api/sessions/' + state['id'] + '/workspace')
        self.assertEqual(result.status_code, 200, result.json)
        return next(card for card in result.json['generation']['cards'] if card['id'] == target)

    def generate(self, state, target, *, edit=False):
        card = self.card(state, target)
        body = {'confirmed_revision': card['generation_revision'], 'card_revision': card['card_revision'],
                'operation_id': uuid4().hex}
        if edit:
            body.update(parent_run_id=card['selected_run'], feedback='Change background only')
        return self.client.post('/api/sessions/' + state['id'] + ('/revise/' if edit else '/generate/') + target,
                                headers=fixtures.HEADERS, json=body)

    def respond(self, request):
        message = BytesParser().parsebytes(('Content-Type: ' + request.headers['content-type'] + '\r\n\r\n').encode() + request.read())
        parts = message.get_payload()
        fields = {p.get_param('name', header='content-disposition'): p.get_payload(decode=True).decode()
                  for p in parts if not p.get_filename()}
        self.wire.append({'size': fields['size'], 'prompt': fields['prompt'],
                          'files': [p.get_filename() for p in parts if p.get_filename()]})
        size = tuple(map(int, fields['size'].split('x')))
        # Distinct bytes per Run also catch substituting a newer unpassed result.
        output = cp1.picture(('red', 'blue', 'green', 'orange', 'purple')[len(self.wire) % 5], size)
        return httpx.Response(200, json={'data': [{'b64_json': base64.b64encode(output).decode()}]},
                              headers={'x-request-id': 'req_anonymous_per_output'})

    def test_quick_three_distinct_sizes_wire_context_edit_pass_export_and_restart(self):
        mapping = dict(zip(('reference_101', 'reference_102', 'reference_103'), self.sizes))
        state = self.create(sizes=mapping).json['state']
        folder = self.store.folder(state['id'])
        application = app.create_local_debug_app(self.fx.runtime, execution_mode='LIVE DEBUG', allow_runtime_tasks=True)
        inspector = application.test_client()
        blank = inspector.get('/api/inspector/tasks/' + state['id'] + '?image_id=reference_101').json
        self.assertTrue(blank['graph_view']['awaiting_run'])
        self.assertIsNone(blank['selection']['run_id'])
        runs = []
        with self.fx.with_sdk(self.respond):
            for target, size in mapping.items():
                result = self.generate(state, target)
                self.assertEqual(result.status_code, 200, result.json)
                runs.append(result.json['run_id'])
                card = self.card(state, target)
                self.assertEqual(card['output_size'], size)
                run = folder / f"generations/000001/{target}/runs/{result.json['run_id']}"
                self.assertEqual(json.loads((run/'request.json').read_text())['size'], size)
                self.assertEqual(json.loads((run/'plan.json').read_text())['output_size'], size)
                view = inspector.get('/api/inspector/tasks/' + state['id'] + '?image_id=' + target).json
                request_card = next(c for c in view['context_view']['cards'] if c['id'] == 'request')
                self.assertEqual(next(f['value'] for f in request_card['fields'] if f['label'] == '尺寸'), size)
                self.assertEqual([i['role'] for i in request_card['images']], ['product'] * 3 + ['design_reference'])
            first = self.card(state, 'reference_101')
            accepted = self.client.post('/api/sessions/' + state['id'] + '/review/reference_101', headers=fixtures.HEADERS,
                json={'confirmed_revision': 1, 'card_revision': first['card_revision'], 'action': 'pass', 'run_id': runs[0]})
            self.assertEqual(accepted.status_code, 200, accepted.json)
            edited = self.generate(state, 'reference_101', edit=True)
            self.assertEqual(edited.status_code, 200, edited.json)
        self.assertEqual([row['size'] for row in self.wire], self.sizes + [self.sizes[0]])
        self.assertEqual(self.wire[3]['files'][0], 'current_image.png')
        revised_folder = folder / f"generations/000001/reference_101/runs/{edited.json['run_id']}"
        self.assertEqual(json.loads((revised_folder/'run.json').read_text())['parent_run_id'], runs[0])
        self.assertEqual(self.card(state, 'reference_101')['passed_run'], runs[0])
        downloaded = self.client.post('/api/sessions/' + state['id'] + '/export-passed', headers=fixtures.HEADERS)
        with zipfile.ZipFile(io.BytesIO(downloaded.data)) as archive:
            self.assertEqual(archive.namelist(), ['图片_01_V1.png'])
            self.assertNotEqual(archive.read(archive.namelist()[0]), (revised_folder/'image.png').read_bytes())
        restored = app.create_app(self.fx.runtime).test_client().get('/api/sessions/' + state['id']).json['state']
        self.assertEqual(restored['image_sizes'], mapping)

    def test_listing_analysis_confirmation_and_generation_keep_independent_sizes(self):
        mapping = dict(zip(('reference_001', 'reference_002', 'reference_003'), self.sizes))
        state = self.create('product_pack', mapping).json['state']
        self.assertEqual(self.generate(state, 'reference_001').status_code, 409)
        planner = planning_fixtures.PreparePlanTests()
        planner.setUp()
        self.addCleanup(planner.doCleanups)
        with planner.with_ai():
            understood = self.client.post('/api/sessions/' + state['id'] + '/action', headers=fixtures.HEADERS,
                json={'action': 'understand', 'revision': state['revision']})
        self.assertEqual(understood.status_code, 200, understood.json)
        state = understood.json['state']
        for target in mapping:
            result = self.client.post('/api/sessions/' + state['id'] + '/action', headers=fixtures.HEADERS,
                json={'action': 'confirm', 'target': target, 'revision': state['revision'],
                      'plan_version': state['plan_status'][target]['plan_version']})
            self.assertEqual(result.status_code, 200, result.json)
            state = result.json['state']
        with self.fx.with_sdk(self.respond):
            for target in mapping:
                self.assertEqual(self.generate(state, target).status_code, 200)
            self.assertEqual(self.generate(state, 'reference_002', edit=True).status_code, 200)
        self.assertEqual([row['size'] for row in self.wire], self.sizes + [self.sizes[1]])

    def test_invalid_sizes_and_foreign_targets_are_rejected_before_writes(self):
        before = sorted((self.fx.runtime/'sessions').iterdir())
        for sizes in ({'reference_101': '800x800'}, {'reference_999': '1024x1024'},
                      {'product_001': '1024x1024'}, {'../outside': '1024x1024'}, [], 'bad', {'reference_101': None}):
            with self.subTest(sizes=sizes):
                self.assertEqual(self.create(sizes=sizes).status_code, 400)
        self.assertEqual(self.create(image_sizes='null').status_code, 400)
        self.assertEqual(self.create(image_sizes='{').status_code, 400)
        self.assertEqual(sorted((self.fx.runtime/'sessions').iterdir()), before)
        self.assertEqual(self.fx.requests, [])

    def test_copy_requires_explicit_sizes_and_preserves_old_bytes(self):
        state = self.create(sizes={'reference_101': '1024x1024'}).json['state']
        folder = self.store.folder(state['id'])
        before = {p: p.read_bytes() for p in folder.rglob('*') if p.is_file()}
        form = {'mode': 'quick_redesign', 'title': 'copy', 'from_session': state['id'],
                'keep_images': json.dumps([i['id'] for i in state['images']]), 'quick_business_version': 'v1',
                'quick_slots': json.dumps(state['quick_slots'])}
        self.assertEqual(self.client.post('/api/sessions', headers=fixtures.HEADERS, data=form).status_code, 400)
        form['image_sizes'] = json.dumps({'reference_101': '1536x1024'})
        copied = self.client.post('/api/sessions', headers=fixtures.HEADERS, data=form)
        self.assertEqual(copied.status_code, 200, copied.json)
        self.assertNotEqual(copied.json['state']['id'], state['id'])
        self.assertEqual(copied.json['state']['image_sizes'], {'reference_101': '1536x1024'})
        self.assertEqual(before, {p: p.read_bytes() for p in folder.rglob('*') if p.is_file()})

    def test_tampered_sizes_block_generation_without_calls_and_legacy_defaults_remain(self):
        state = self.create().json['state']
        self.assertNotIn('image_sizes', state)
        self.assertEqual(self.card(state, 'reference_101')['output_size'], '1536x1024')
        self.assertEqual(self.card(self.fx.state, 'reference_001')['output_size'], '1024x1536')
        state['image_sizes'] = {'reference_101': 'auto'}
        (self.store.folder(state['id'])/'state.json').write_text(json.dumps(state))
        self.assertEqual(self.client.get('/api/sessions/' + state['id'] + '/workspace').status_code, 409)
        self.assertEqual(self.fx.requests, [])

    def test_developer_navigation_is_explicit_local_only_and_keeps_normal_api_closed(self):
        page = self.client.get('/workspace/new').get_data(as_text=True)
        self.assertIn('开发者视图 / Live Debug', page)
        self.assertIn('./scripts/start_live_debug.sh', page)
        self.assertNotIn('id="toggle-inspector"', page)
        self.assertEqual(self.client.get('/api/inspector/tasks').status_code, 404)
        remote = self.client.get('/workspace/new', environ_overrides={'REMOTE_ADDR': '192.168.0.2'}).get_data(as_text=True)
        self.assertNotIn('id="live-debug-entry"', remote)
        state = self.create().json['state']
        debug = app.create_local_debug_app(self.fx.runtime, execution_mode='LIVE DEBUG', allow_runtime_tasks=True).test_client()
        page = debug.get('/workspace/' + state['id']).get_data(as_text=True)
        self.assertIn('开发者视图 / Inspector', page)
        self.assertIn('id="toggle-inspector"', page)
        self.assertFalse((self.store.folder(state['id'])/'generations').exists())
        self.assertEqual(debug.post('/api/inspector/tasks', headers=fixtures.HEADERS).status_code, 405)


if __name__ == '__main__':
    unittest.main()
