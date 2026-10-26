"""CP2: browser-facing contracts and saved-Evidence projection, temporary data only."""

import io
import json
from pathlib import Path
import shutil
import subprocess
import unittest

import app
from image_workflow.inspector import InspectorReader, InspectorError
from image_workflow.inspector_graph import prompt_segments
import test_quick_v1 as cp1


class QuickV1WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.fx = cp1.QuickV1Tests()
        self.fx.setUp()
        self.addCleanup(self.fx.doCleanups)

    def view(self, target='reference_102', run=None):
        return InspectorReader(self.fx.fx.runtime, [self.fx.state['id']]).inspect(
            self.fx.state['id'], target, self.fx.state['revision'], run)

    def test_v1_projection_uses_output_identity_and_all_product_roles_without_rewriting(self):
        with self.fx.fx.with_sdk():
            result = self.fx.generate('reference_102')
        run = result.json['run_id']
        before = {p: p.read_bytes() for p in self.fx.folder.rglob('*') if p.is_file()}
        view = self.view(run=run)
        self.assertEqual([image['id'] for image in view['images']], ['reference_101', 'reference_102', 'reference_103'])
        cards = {card['id']: card for card in view['context_view']['cards']}
        self.assertEqual([image['id'] for image in cards['product']['images']], ['product_001', 'product_002', 'product_003'])
        self.assertEqual([image['id'] for image in cards['references']['images']], ['reference_002'])
        self.assertTrue(all(field['status'] == 'OBSERVED' for field in cards['assembly']['fields']))
        self.assertEqual([field['value'] for field in cards['requirements']['fields'][3:]],
                         ['dimensions', 'reference_002', '只表达自家尺寸图中有依据的尺寸'])
        self.assertEqual(cards['assembly']['checks'][0]['result'], 'MATCH')
        edge = next(edge for edge in view['graph_view']['edges'] if edge['key'] == 'E11')
        self.assertEqual(edge['evidence_status'], 'OBSERVED')
        self.assertIn('text_span', edge['evidence_refs'][-1])
        self.assertEqual(before, {p: p.read_bytes() for p in self.fx.folder.rglob('*') if p.is_file()})
        with self.assertRaises(InspectorError):
            self.view('product_001', run)

    def test_unexecuted_missing_context_and_edited_run_keep_evidence_boundaries(self):
        self.assertTrue(self.view()['graph_view']['awaiting_run'])
        with self.fx.fx.with_sdk():
            generated = self.fx.generate()
            edited = self.fx.edit(auxiliary=self.fx.sources[0])
        run = edited.json['run_id']
        view = self.view('reference_101', run)
        request = next(card for card in view['context_view']['cards'] if card['id'] == 'request')
        self.assertEqual([image['role'] for image in request['images']],
                         ['current_image', 'product', 'product', 'product', 'design_reference', 'auxiliary_reference'])
        record = json.loads((self.fx.run_folder(run)/'run.json').read_text())
        self.assertEqual(record['parent_run_id'], generated.json['run_id'])
        (self.fx.run_folder(run)/'plan.json').unlink()  # anonymous missing-record fixture only
        cards = {card['id']: card for card in self.view('reference_101', run)['context_view']['cards']}
        self.assertTrue(all(field['status'] == 'UNKNOWN' for field in cards['assembly']['fields']))
        self.assertEqual(len(cards['product']['images']), 3)
        self.assertEqual([image['role'] for image in cards['references']['images']],
                         ['current_image', 'design_reference', 'auxiliary_reference'])

    def test_save_as_with_replacement_remaps_reference_without_changing_old_runs_or_pass(self):
        with self.fx.fx.with_sdk():
            generated = self.fx.generate()
        self.assertEqual(self.fx.review('pass', generated.json['run_id']).status_code, 200)
        before = {p: p.read_bytes() for p in self.fx.folder.rglob('*') if p.is_file()}
        configuration = [{'id': 'reference_101', 'type': 'main', 'enabled': True, 'reference_id': 'reference_002', 'requirements': ''}]
        result = self.fx.client.post('/api/sessions', headers={'X-Local-Action': 'prepare-plan'}, data={
            'mode': 'quick_redesign', 'title': 'Anonymous separate copy', 'requirements': '另存',
            'from_session': self.fx.state['id'], 'keep_images': json.dumps(['product_001', 'product_002', 'product_003', 'reference_003']),
            'quick_business_version': 'v1', 'quick_slots': json.dumps(configuration),
            'reference': (io.BytesIO(self.fx.references[0]), 'replacement.png')})
        self.assertEqual(result.status_code, 200, result.json)
        saved = result.json['state']
        self.assertNotEqual(saved['id'], self.fx.state['id'])
        self.assertEqual(self.fx.cards(saved)[0]['reference']['url'].split('/')[-1], 'reference_002')
        self.assertEqual(self.fx.cards(saved)[0]['versions'], [])
        self.assertEqual(before, {p: p.read_bytes() for p in self.fx.folder.rglob('*') if p.is_file()})

    def test_v1_label_matching_never_claims_ambiguous_or_missing_text_matches(self):
        self.assertEqual(prompt_segments('整体要求：\nx', 'operator_design_requirements', quick_v1=True), [])
        prompt = '\n整体要求：\nx\n整体要求：\ny\n商品事实说明：\nz\n'
        self.assertEqual(prompt_segments(prompt, 'operator_design_requirements', quick_v1=True), [])

    def test_local_inspector_api_switches_v1_outputs_and_preserves_read_only_guards(self):
        application = app.create_local_debug_app(self.fx.fx.runtime, execution_mode='LIVE DEBUG',
                                                 allow_runtime_tasks=True, allow_paid_actions=True)
        client = application.test_client()
        with self.fx.fx.with_sdk():
            result = self.fx.generate()
        url = '/api/inspector/tasks/' + self.fx.state['id']
        before = {p: p.read_bytes() for p in self.fx.folder.rglob('*') if p.is_file()}
        view = client.get(url + '?image_id=reference_101&revision=1&run_id=' + result.json['run_id'])
        self.assertEqual(view.status_code, 200, view.json)
        self.assertTrue(view.json['graph_view']['supported'])
        self.assertTrue(client.get(url + '?image_id=reference_102').json['graph_view']['awaiting_run'])
        # Satisfy the existing app-wide CSRF guard before exercising Inspector's
        # independent read-only guard; requests without the header remain 403.
        self.assertEqual(client.post(url).status_code, 403)
        self.assertEqual(client.post(url, headers={'X-Local-Action': 'prepare-plan'}).status_code, 405)
        self.assertEqual(client.get('/api/inspector/tasks/' + 'f' * 32).status_code, 404)
        self.assertEqual(before, {p: p.read_bytes() for p in self.fx.folder.rglob('*') if p.is_file()})


class QuickV1UploadNodeTests(unittest.TestCase):
    def test_upload_ui_contracts(self):
        node = shutil.which('node')
        if not node:
            self.skipTest('Node is not installed; upload interactions NOT RUN')
        result = subprocess.run([node, '--test', str(Path(__file__).with_name('quick_v1_upload.test.cjs'))],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
