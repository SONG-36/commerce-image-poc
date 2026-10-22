"""I02 offline integration: real SDK multipart, synthetic files, no paid API."""

import io
import json
from pathlib import Path
import threading
import unittest
from unittest.mock import patch
from uuid import uuid4
import zipfile

import httpx
from PIL import Image
import test_generate_plan_image as fixtures
from image_workflow.generation import auxiliary as image_review


def auxiliary_bytes(format="PNG", color="blue"):
    stream = io.BytesIO()
    Image.new("RGB", (37, 41), color).save(stream, format)
    return stream.getvalue()


class ImageGuidedEditingTests(unittest.TestCase):
    def setUp(self):
        self.fx = fixtures.GenerationPageTests()
        self.fx.setUp()
        self.addCleanup(self.fx.doCleanups)
        self.client, self.store = self.fx.client, self.fx.store
        quick = self.store.create({"listing": "", "description": "", "requirements": "商业信息图，保留原文",
                                   "product_facts": "不得添加配件"},
            [("product", "原图1.png", fixtures.png()), ("product", "原图2.png", fixtures.png()),
             ("reference", "风格参考.png", fixtures.png())], "I02 OFFLINE QUICK", mode="quick_redesign")
        self.states = (self.fx.state, quick)
        with self.fx.with_sdk():
            for state in self.states:
                service = self.fx.app.extensions['generation_service']
                result = service.generate(state, self.target(state))
                self.assertEqual(result['status'], 'SUCCEEDED')

    def target(self, state):
        return "product_001" if state.get("mode") == "quick_redesign" else "reference_001"

    def card(self, state):
        return self.client.get(f"/api/sessions/{state['id']}/generation").json['cards'][0]

    def edit(self, state, data=None, purpose="product_appearance", *, feedback="仅修正商品外观，保留布局与文字",
             operation=None, parent=None, revision=None, files=None):
        card = self.card(state)
        body = {"confirmed_revision": state['revision'], "card_revision": card['card_revision'] if revision is None else revision,
                "parent_run_id": parent or card['selected_run'], "operation_id": operation or uuid4().hex, "feedback": feedback}
        url = f"/api/sessions/{state['id']}/revise/{self.target(state)}"
        if data is None and files is None:
            return self.client.post(url, headers=fixtures.HEADERS, json=body)
        body = {key: str(value) for key, value in body.items()}
        if purpose is not None:
            body['auxiliary_purpose'] = purpose
        body.update(files or {'auxiliary': (io.BytesIO(data), '本次辅助图.png')})
        response = self.client.post(url, headers=fixtures.HEADERS, data=body)
        response.request.input_stream.close()  # Close the test builder's large multipart temporary body.
        return response

    def folder(self, state, run_id):
        return self.fx.app.extensions['generation_service'].run_folder(state['id'], state['revision'], self.target(state), run_id)

    def pass_current(self, state):
        card = self.card(state)
        result = self.client.post(f"/api/sessions/{state['id']}/review/{self.target(state)}", headers=fixtures.HEADERS,
            json={"confirmed_revision": state['revision'], "card_revision": card['card_revision'],
                  "action": "pass", "run_id": card['selected_run']})
        self.assertEqual(result.status_code, 200)
        return card['selected_run']

    def test_three_roles_send_actual_new_image_and_context_in_both_modes(self):
        for state in self.states:
            original = {p: p.read_bytes() for p in self.store.folder(state['id']).rglob('*') if p.is_file() and p.name != 'current.json'}
            for purpose, label in image_review.AUXILIARY_PURPOSES.items():
                with self.subTest(mode=state.get('mode'), purpose=purpose), self.fx.with_sdk():
                    result = self.edit(state, auxiliary_bytes(), purpose)
                    self.assertEqual(result.status_code, 200, result.json)
                    folder = self.folder(state, result.json['run_id'])
                    request = json.loads((folder / 'request.json').read_text())
                    record = json.loads((folder / 'run.json').read_text())
                    context = json.loads((folder / 'plan.json').read_text())
                    order = request['image_order']
                    self.assertEqual(order[0]['role'], 'current_image')
                    self.assertEqual(order[-1]['role'], 'auxiliary_reference')
                    self.assertEqual(order[-1]['purpose'], purpose)
                    self.assertEqual(order[-1]['session_id'], state['id'])
                    self.assertEqual(order[-1]['image_id'], self.target(state))
                    self.assertEqual(order[-1]['scope'], 'current_image_only')
                    self.assertEqual((folder / order[-1]['file']).read_bytes(), auxiliary_bytes())
                    wire = self.fx.requests[-1].read()
                    self.assertIn(b'filename="current_image.png"', wire)
                    self.assertIn(b'filename="auxiliary_reference.png"', wire)
                    self.assertIn(auxiliary_bytes(), wire)
                    self.assertIn(label, request['prompt'])
                    self.assertIn(f"图片 {len(order)}（auxiliary_reference）", request['prompt'])
                    self.assertIn(state['inputs']['requirements'], request['prompt'])
                    self.assertEqual(request['prompt'], (folder / 'prompt.txt').read_text())
                    self.assertEqual(context['auxiliary_reference'], record['auxiliary_reference'])
                    if state.get('mode') == 'quick_redesign':
                        self.assertNotIn('confirmed_plan', context)
                        self.assertEqual([i['id'] for i in order], ['current_image', 'product_001', 'reference_001', 'auxiliary_reference'])
                    else:
                        self.assertEqual(context['confirmed_plan'], state['plans']['reference_001'])
                        self.assertIn(state['inputs']['listing'], request['prompt'])
                        self.assertNotIn('reference_002', request['prompt'])
                    self.assertEqual(record['usage']['total_tokens'], 30)
                    self.assertEqual(record['request_id'], 'req_offline_generation')
                    self.assertTrue((folder / 'response.json').is_file())
                    for item in order:
                        self.assertEqual(fixtures.generation.sha256((folder / item['file']).read_bytes()), item['sha256'])
            for path, data in original.items():
                self.assertEqual(path.read_bytes(), data)
            other_cards = self.client.get(f"/api/sessions/{state['id']}/generation").json['cards'][1:]
            self.assertTrue(all(not c['versions'] for c in other_cards))

    def test_text_only_edit_does_not_implicitly_resend_previous_auxiliary_or_feedback(self):
        for state in self.states:
            with self.fx.with_sdk():
                first = self.edit(state, auxiliary_bytes(), feedback='UNIQUE_PREVIOUS_EDIT_ONLY').json['run_id']
                second = self.edit(state, feedback='本次只调整字体').json['run_id']
            folder = self.folder(state, second)
            request = json.loads((folder / 'request.json').read_text())
            self.assertNotIn('auxiliary_reference', request['prompt'])
            self.assertNotIn('UNIQUE_PREVIOUS_EDIT_ONLY', request['prompt'])
            self.assertNotIn(b'filename="auxiliary_reference.png"', self.fx.requests[-1].read())
            self.assertTrue((self.folder(state, first) / 'inputs/auxiliary_reference.png').is_file())
            self.assertEqual(self.card(state)['versions'][-1]['parent_run_id'], first)

    def test_upload_formats_are_verified_by_bytes_and_preserved_without_reencoding(self):
        state = self.states[0]
        for format, extension in [('PNG', 'png'), ('JPEG', 'jpg'), ('WEBP', 'webp')]:
            data = auxiliary_bytes(format)
            with self.fx.with_sdk():
                result = self.edit(state, data)
            self.assertEqual(result.status_code, 200, result.json)
            folder = self.folder(state, result.json['run_id'])
            self.assertEqual((folder / f'inputs/auxiliary_reference.{extension}').read_bytes(), data)
            record = json.loads((folder / 'run.json').read_text())
            self.assertEqual(record['auxiliary_reference']['mime'], {'jpg': 'image/jpeg', 'png': 'image/png', 'webp': 'image/webp'}[extension])

    def test_invalid_upload_role_count_size_and_request_metadata_stop_before_model(self):
        state = self.states[0]
        original = {p: p.read_bytes() for p in self.store.root.rglob('*') if p.is_file()}
        count = len(self.fx.requests)
        cases = [(b'not an image', 'product_appearance'), (auxiliary_bytes('GIF'), 'design_style'),
                 (auxiliary_bytes(), None), (auxiliary_bytes(), 'unknown'),
                 (auxiliary_bytes() + b'sk-offline-secret-in-image-metadata', 'product_appearance'),
                 (b'x' * (image_review.MAX_AUXILIARY_BYTES + 1), 'local_content')]
        for data, purpose in cases:
            self.assertEqual(self.edit(state, data, purpose).status_code, 400)
        two = {'auxiliary': [(io.BytesIO(auxiliary_bytes()), 'one.png'), (io.BytesIO(auxiliary_bytes()), 'two.png')]}
        self.assertEqual(self.edit(state, files=two).status_code, 400)
        self.assertEqual(self.edit(state, files={'foreign_image': (io.BytesIO(auxiliary_bytes()), 'one.png')}).status_code, 400)
        self.assertEqual(self.edit(state, files={'auxiliary': (io.BytesIO(auxiliary_bytes()), 'one.png')}, revision='invalid').status_code, 400)
        self.assertEqual(len(self.fx.requests), count)
        for path, data in original.items():
            self.assertEqual(path.read_bytes(), data)

    def test_cross_task_parent_and_json_server_path_are_refused(self):
        state, foreign = self.states
        before = {p: p.read_bytes() for p in self.store.root.rglob('*') if p.is_file()}
        self.assertEqual(self.edit(state, auxiliary_bytes(), parent=self.card(foreign)['selected_run']).status_code, 409)
        card = self.card(state)
        body = {'confirmed_revision': state['revision'], 'card_revision': card['card_revision'],
                'parent_run_id': card['selected_run'], 'operation_id': uuid4().hex, 'feedback': '测试',
                'auxiliary_path': '../other-task/inputs/product_001.png', 'auxiliary_purpose': 'product_appearance'}
        result = self.client.post(f"/api/sessions/{state['id']}/revise/{self.target(state)}", json=body, headers=fixtures.HEADERS)
        self.assertEqual(result.status_code, 400)
        self.assertEqual(len(self.fx.requests), 2)  # Only the two setup generations.
        for path, data in before.items():
            self.assertEqual(path.read_bytes(), data)

    def test_new_version_keeps_pass_original_and_final_export_after_restart(self):
        for state in self.states:
            accepted = self.pass_current(state)
            original_image = (self.folder(state, accepted) / 'image.png').read_bytes()
            before = {p: p.read_bytes() for p in self.store.folder(state['id']).rglob('*') if p.is_file() and p.name != 'current.json'}
            with self.fx.with_sdk():
                result = self.edit(state, auxiliary_bytes())
            self.assertEqual(result.status_code, 200, result.json)
            self.assertEqual([v['version'] for v in self.card(state)['versions']], [1, 2])
            self.assertEqual(self.card(state)['passed_run'], accepted)
            self.assertEqual(self.card(state)['versions'][-1]['parent_run_id'], accepted)
            restarted = fixtures.web.create_app(self.fx.runtime).test_client()
            restored = restarted.get(f"/api/sessions/{state['id']}/generation").json['cards'][0]
            self.assertEqual(restored, self.card(state))
            self.assertEqual(restored['versions'][-1]['auxiliary_reference']['purpose'], 'product_appearance')
            result = self.client.post(f"/api/sessions/{state['id']}/export-passed", headers=fixtures.HEADERS)
            with zipfile.ZipFile(io.BytesIO(result.data)) as archive:
                self.assertEqual(archive.namelist(), ['图片_01_V1.png'])
                self.assertEqual(archive.read(archive.namelist()[0]), original_image)
            for path, data in before.items():
                self.assertEqual(path.read_bytes(), data)

    def test_experiment_zip_has_exact_auxiliary_bytes_roles_and_only_own_task(self):
        for state in self.states:
            data = auxiliary_bytes(color='green' if state.get('mode') == 'quick_redesign' else 'blue')
            with self.fx.with_sdk():
                run = self.edit(state, data, 'local_content').json['run_id']
            response = self.client.post(f"/api/sessions/{state['id']}/export-experiment", headers=fixtures.HEADERS)
            self.assertEqual(response.status_code, 200, response.json)
            with zipfile.ZipFile(io.BytesIO(response.data)) as archive:
                root = f"case-{state['id']}-experiment/"
                manifest = json.loads(archive.read(root + 'manifest.json'))
                entry = next(r for r in manifest['runs'] if r['run_id'] == run)
                aux = entry['inputs'][-1]
                self.assertEqual(aux['role'], 'auxiliary_reference')
                self.assertEqual(aux['purpose'], 'local_content')
                self.assertEqual(archive.read(root + aux['file']), data)
                for file in manifest['files']:
                    content = archive.read(root + file['path'])
                    self.assertEqual(fixtures.generation.sha256(content), file['sha256'])
                    self.assertNotIn(b'sk-offline-t03-test-key', content)
                self.assertEqual(manifest['session_id'], state['id'])
                self.assertEqual(len(manifest['runs']), 2)

    def test_api_failure_keeps_auxiliary_evidence_and_previous_pass_no_retry(self):
        for state in self.states:
            accepted = self.pass_current(state)
            count = len(self.fx.requests)
            with self.fx.with_sdk(lambda request: httpx.Response(500, json={'error': {'message': 'offline failure'}})):
                response = self.edit(state, auxiliary_bytes())
            self.assertEqual(response.status_code, 502)
            self.assertEqual(len(self.fx.requests), count + 1)
            self.assertIn('计费尚未确认', response.json['error'])
            card = self.card(state)
            self.assertEqual(card['selected_run'], accepted)
            self.assertEqual(card['passed_run'], accepted)
            self.assertEqual(len(card['versions']), 1)
            folder = self.folder(state, response.json['run_id'])
            self.assertEqual((folder / 'inputs/auxiliary_reference.png').read_bytes(), auxiliary_bytes())
            self.assertTrue((folder / 'request.json').is_file())
            self.assertTrue((folder / 'error.json').is_file())

    def test_idempotency_compares_auxiliary_hash_and_purpose(self):
        state = self.states[0]
        operation, card = uuid4().hex, self.card(state)
        with self.fx.with_sdk():
            first = self.edit(state, auxiliary_bytes(), operation=operation)
        replay = self.edit(state, auxiliary_bytes(), operation=operation, revision=card['card_revision'], parent=card['selected_run'])
        self.assertEqual(replay.json['run_id'], first.json['run_id'])
        for data, purpose in [(auxiliary_bytes(color='white'), 'product_appearance'), (auxiliary_bytes(), 'design_style')]:
            self.assertEqual(self.edit(state, data, purpose, operation=operation, parent=card['selected_run']).status_code, 409)
        self.assertEqual(self.edit(state, operation=operation, parent=card['selected_run']).status_code, 409)
        self.assertEqual(len(self.fx.requests), 3)

    def test_pending_image_edit_rejects_parallel_submission_without_retry(self):
        state = self.states[0]
        entered, release = threading.Event(), threading.Event()
        def handler(request):
            entered.set()
            if not release.wait(5):
                raise AssertionError('offline test timed out')
            return httpx.Response(500, json={'error': {'message': 'offline failure'}})
        results = []
        with self.fx.with_sdk(handler):
            thread = threading.Thread(target=lambda: results.append(self.edit(state, auxiliary_bytes())))
            thread.start()
            try:
                self.assertTrue(entered.wait(5))
                self.assertEqual(self.card(state)['status'], 'RUNNING')
                self.assertEqual(self.edit(state, auxiliary_bytes()).status_code, 409)
            finally:
                release.set()
                thread.join(5)
        self.assertEqual(results[0].status_code, 502)
        self.assertEqual(len(self.fx.requests), 3)


if __name__ == '__main__':
    unittest.main()
