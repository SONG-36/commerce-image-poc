"""Unified UI read model and unchanged mutation guards, using temporary Mock runs."""

import hashlib
import io
import json
import unittest
from uuid import uuid4

import test_generate_plan_image as fixtures
import test_prepare_plan as planning


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.fx = fixtures.GenerationPageTests()
        self.fx.setUp()
        self.addCleanup(self.fx.doCleanups)
        self.client, self.store, self.state = self.fx.client, self.fx.store, self.fx.state
        self.planner = planning.PreparePlanTests()
        self.planner.requests = []

    def view(self, state=None, client=None):
        state = state or self.state
        return (client or self.client).get(f"/api/sessions/{state['id']}/workspace")

    def files(self):
        return {str(p.relative_to(self.fx.runtime)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in self.fx.runtime.rglob('*') if p.is_file()}

    def action(self, state, action, target=None, feedback=''):
        return self.client.post(f"/api/sessions/{state['id']}/action", headers=fixtures.HEADERS,
                                json=dict(revision=state['revision'], action=action, target=target, feedback=feedback))

    def test_workspace_and_legacy_entries_read_only_dynamic_and_free(self):
        before = self.files()
        for path in ['/workspace/new', '/prepare/new', f"/workspace/{self.state['id']}",
                     f"/prepare/{self.state['id']}", f"/generate/{self.state['id']}"]:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            for marker in [b'data-workspace="true"', b'id="input-panel"', b'id="generation-cards"', b'/static/workspace.js']:
                self.assertIn(marker, response.data)
        view = self.view().json
        self.assertTrue(view['generation_allowed'])
        self.assertFalse(view['historical_generation'])
        self.assertEqual(len(view['generation']['cards']), 3)
        self.assertEqual(view['generation']['cards'], self.fx.cards().json['cards'])
        self.assertEqual(self.files(), before)
        self.assertEqual(self.fx.requests, [])
        task = next(t for t in self.client.get('/api/tasks').json['tasks'] if t['id'] == self.state['id'])
        self.assertEqual(task['url'], '/workspace/' + self.state['id'])

    def test_plan_edit_keeps_old_image_read_only_and_requires_new_confirmation(self):
        target = fixtures.web.reference_ids(self.state)[0]
        with self.fx.with_sdk():
            self.assertEqual(self.fx.post(target).status_code, 200)
        old = self.view().json['generation']['cards'][0]
        image_bytes = self.client.get(old['image_url']).data
        with self.planner.with_ai():
            response = self.action(self.state, 'plan', target, '本张采用浅粉色背景，保留商品外观')
        self.assertEqual(response.status_code, 200, response.json)
        changed = response.json['state']
        view = self.view().json
        self.assertTrue(view['generation_allowed'])  # Other confirmed cards remain usable.
        self.assertTrue(view['historical_generation'])
        self.assertEqual(view['generation']['cards'][0]['confirmed_revision'], self.state['revision'])
        self.assertFalse(view['generation']['cards'][0]['generation_allowed'])
        self.assertTrue(view['generation']['cards'][1]['generation_allowed'])
        self.assertEqual(view['state']['plans'][target]['design'], '本张采用浅粉色背景，保留商品外观')
        self.assertEqual(view['generation']['cards'][0]['image_url'], old['image_url'])
        self.assertEqual(self.client.get(old['image_url']).data, image_bytes)
        for endpoint in ['generate', 'revise', 'review']:
            result = self.client.post(f"/api/sessions/{changed['id']}/{endpoint}/{target}",
                                      headers=fixtures.HEADERS, json={'confirmed_revision': changed['revision']})
            self.assertEqual(result.status_code, 409)
        confirmed = self.action(changed, 'confirm', target).json['state']
        view = self.view().json
        self.assertTrue(view['generation_allowed'])
        self.assertFalse(view['historical_generation'])
        card = view['generation']['cards'][0]
        self.assertEqual(card['versions'], [])
        self.assertEqual(card['previous_result']['image_url'], old['image_url'])
        with self.fx.with_sdk():
            self.assertEqual(self.fx.post(target, confirmed).status_code, 200)
        self.assertIn('本张采用浅粉色背景'.encode(), self.fx.requests[-1].read())
        self.assertEqual(self.client.get(old['image_url']).data, image_bytes)

    def test_stale_understanding_cannot_be_confirmed_or_generated(self):
        with self.planner.with_ai():
            response = self.action(self.state, 'product', feedback='修正商品理解，不增加新功能')
        changed = response.json['state']
        self.assertTrue(self.view().json['state']['stale_plans'])
        self.assertFalse(self.view().json['generation_allowed'])
        self.assertEqual(self.action(changed, 'confirm').status_code, 400)
        self.assertEqual(self.fx.post(fixtures.web.reference_ids(changed)[0], changed).status_code, 409)
        self.assertEqual(self.fx.requests, [])

    def test_quick_multi_image_creation_copy_restore_and_task_isolation(self):
        original = self.files()
        response = self.client.post('/api/sessions', headers=fixtures.HEADERS, data={
            'title': '统一工作台离线重设计', 'mode': 'quick_redesign', 'requirements': '保留外观，优化排版',
            'product': [(io.BytesIO(fixtures.png()), f'原图{i}.png') for i in range(2)]})
        self.assertEqual(response.status_code, 200, response.json)
        quick = response.json['state']
        self.assertFalse(quick['confirmed'])
        self.assertEqual(quick['plans'], {})
        view = self.view(quick).json
        self.assertTrue(view['generation_allowed'])
        self.assertEqual([c['id'] for c in view['generation']['cards']], ['product_001', 'product_002'])
        copy = self.client.post('/api/sessions', headers=fixtures.HEADERS, data={
            'title': '另存任务', 'mode': 'quick_redesign', 'from_session': quick['id'],
            'keep_images': json.dumps([i['id'] for i in quick['images']]), 'requirements': '不同任务要求'})
        self.assertEqual(copy.status_code, 200, copy.json)
        copied = copy.json['state']
        self.assertNotEqual(copied['id'], quick['id'])
        with self.fx.with_sdk():
            generated = self.client.post(f"/api/sessions/{quick['id']}/generate/product_001", headers=fixtures.HEADERS,
                                         json={'confirmed_revision': quick['revision'], 'card_revision': 0,
                                               'operation_id': uuid4().hex})
            self.assertEqual(generated.status_code, 200, generated.json)
        cards = self.view(quick).json['generation']['cards']
        self.assertEqual(len(cards[0]['versions']), 1)
        self.assertEqual(cards[1]['versions'], [])
        self.assertEqual(self.view(copied).json['generation']['cards'][0]['versions'], [])
        restarted = fixtures.web.create_app(self.fx.runtime).test_client()
        self.assertEqual(self.view(quick, restarted).json['generation']['cards'], cards)
        after = self.files()
        for path, digest in original.items():
            if path.startswith(f"sessions/{self.state['id']}/"):
                self.assertEqual(after[path], digest)

    def test_history_scope_rejects_other_task_and_read_failure_never_mutates(self):
        target = fixtures.web.reference_ids(self.state)[0]
        with self.fx.with_sdk():
            self.assertEqual(self.fx.post(target).status_code, 200)
        changed = self.store.load(self.state['id'])
        changed['confirmed'] = False
        self.store.save(changed, {'action': 'offline_unconfirm'})
        version = self.store.folder(changed['id']) / f"versions/{self.state['revision']:06}.json"
        bad = json.loads(version.read_text())
        bad['id'] = 'f' * 32
        version.write_text(json.dumps(bad))
        before = self.files()
        self.assertEqual(self.view().status_code, 409)
        self.assertEqual(self.files(), before)


if __name__ == '__main__':
    unittest.main()
