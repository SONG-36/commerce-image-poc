"""V0.7 graph contracts over NEW anonymous SDK-Mock evidence, never a live API."""

import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

import app
from file_ops import sha256
from image_workflow.inspector import InspectorReader
from image_workflow.inspector_graph import context_graph
from test_context_inspector import make_quick_evidence, mock_client, anonymous_image, CANARY, HEADERS


class ContextFlowGraphTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / 'new-anonymous-fixture'
        self.enterContext(patch('socket.socket.connect', side_effect=AssertionError('No network')))
        self.business, self.state, self.run, self.calls = make_quick_evidence(self.root)
        self.reader = InspectorReader(self.root, [self.state['id']])
        self.folder = self.root / 'sessions' / self.state['id'] / 'generations/000001/product_001/runs' / self.run

    def graph(self, **selection):
        return self.reader.inspect(self.state['id'], **selection)['graph_view']

    def test_graph_contract_counts_stable_ids_and_exact_scope(self):
        graph = self.graph()
        self.assertEqual(len(graph['nodes']), 17)
        self.assertEqual(len(graph['edges']), 21)
        self.assertEqual(sum(n['default_visible'] for n in graph['nodes']), 12)
        self.assertEqual(sum(n['kind'] == 'ACTIVITY' for n in graph['nodes']), 3)
        ids = {n['id'] for n in graph['nodes']}
        self.assertEqual(len(ids), 17)
        self.assertEqual(graph, self.graph())
        for value in graph['selection'].values():
            self.assertIn(str(value), graph['graph_id'])
        self.assertEqual({e['relation_type'] for e in graph['edges']},
                         {'USED_AS', 'INCLUDED_IN', 'ASSEMBLED_INTO', 'SUBMITTED_WITH', 'PRODUCED'})
        for edge in graph['edges']:
            self.assertIn(edge['source'], ids)
            self.assertIn(edge['target'], ids)
            self.assertTrue(edge['evidence_refs'])
            self.assertTrue(edge['uncertainty_reason'])
            self.assertIn('consistency_checks', edge)

    def test_no_run_does_not_fabricate_a_run_graph_or_file_paths(self):
        store = self.business.extensions['plan_store']
        state = store.create({'listing': '', 'description': '', 'requirements': '匿名新任务'},
                             [('product', 'new.png', anonymous_image())], 'NEW FIXTURE · 尚未生成', mode='quick_redesign')
        reader = InspectorReader(self.root, [state['id']])
        view = reader.inspect(state['id'])
        self.assertIsNone(view['selection']['run_id'])
        self.assertEqual(view['graph_view']['nodes'], [])
        self.assertTrue(view['graph_view']['awaiting_run'])

    def test_observed_text_relationship_points_to_saved_unicode_span(self):
        graph = self.graph()
        request = json.loads((self.folder / 'request.json').read_text())
        context = json.loads((self.folder / 'plan.json').read_text())
        for key, field in [('E11', 'requirements'), ('E12', 'product_facts')]:
            edge = next(e for e in graph['edges'] if e['key'] == key)
            self.assertEqual(edge['evidence_status'], 'OBSERVED')
            span = edge['evidence_refs'][1]['text_span']
            self.assertEqual(request['prompt'][span['start']:span['end']], context['original_inputs'][field])
            self.assertEqual(edge['consistency_checks'][0]['result'], 'MATCH')

    def test_quick_semantics_and_local_attempt_are_not_remote_or_review_proof(self):
        graph = self.graph()
        nodes = {n['key']: n for n in graph['nodes']}
        edges = {e['key']: e for e in graph['edges']}
        self.assertEqual(nodes['P01']['evidence_status'], 'INFERRED')
        self.assertIsNone(nodes['P01']['event_id'])
        self.assertEqual(nodes['N12']['evidence_status'], 'MISSING')
        self.assertEqual(nodes['P03']['execution_status'], 'UNKNOWN')
        self.assertEqual(nodes['N13']['evidence_status'], 'N/A')
        self.assertEqual(nodes['N14']['evidence_status'], 'N/A')
        self.assertEqual(edges['E15']['evidence_status'], 'INFERRED')
        self.assertEqual(edges['E16']['evidence_status'], 'INFERRED')
        self.assertEqual(graph['execution_environment']['value'], 'UNKNOWN')
        self.assertIn('不是独立 Planning', nodes['N06']['summary'])
        self.assertEqual(len(self.calls), 1)  # This fixture's SDK request is MockTransport.

    def test_projection_is_pure_and_reader_leaves_all_evidence_bytes_unchanged(self):
        before = {str(p): sha256(p.read_bytes()) for p in self.root.rglob('*') if p.is_file()}
        view = self.reader.inspect(self.state['id'])
        with patch('builtins.open', side_effect=AssertionError('No graph I/O')):
            graph = context_graph(view['selection'], 'quick_redesign', view['nodes'], view['assets'], view['context_view'])
        self.assertEqual(graph, view['graph_view'])
        self.assertEqual(before, {str(p): sha256(p.read_bytes()) for p in self.root.rglob('*') if p.is_file()})
        self.assertNotIn(CANARY, json.dumps(graph))

    def test_missing_request_cannot_be_rebuilt_from_current_prompt_policy(self):
        (self.folder / 'request.json').unlink()
        graph = self.graph()
        self.assertEqual(next(n for n in graph['nodes'] if n['key'] == 'N09')['evidence_status'], 'MISSING')
        edges = {e['key']: e for e in graph['edges']}
        for key in ('E11', 'E12', 'E13', 'E14', 'E15'):
            self.assertEqual(edges[key]['evidence_status'], 'UNKNOWN')
        self.assertFalse(edges['E11']['evidence_refs'][1]['exists'])

    def test_missing_pointer_or_different_listing_does_not_create_observed_inclusion(self):
        path = self.folder / 'plan.json'
        context = json.loads(path.read_text())
        context['original_inputs'].pop('requirements')
        context['original_inputs']['listing'] = 'DIFFERENT ANONYMOUS LISTING'
        path.write_text(json.dumps(context))
        graph = self.graph()
        edges = {e['key']: e for e in graph['edges']}
        self.assertEqual(edges['E03']['evidence_status'], 'UNKNOWN')
        self.assertFalse(edges['E03']['evidence_refs'][0]['pointer_exists'])
        self.assertEqual(edges['E05']['evidence_status'], 'UNKNOWN')
        self.assertEqual(edges['E05']['consistency_checks'][0]['result'], 'MISMATCH')

    def test_identity_mismatch_and_hash_mismatch_remain_visible(self):
        context = json.loads((self.folder / 'plan.json').read_text())
        context['source_image_id'] = 'product_999'
        (self.folder / 'plan.json').write_text(json.dumps(context))
        (self.folder / 'inputs/product_001.png').write_bytes(anonymous_image('reference'))
        graph = self.graph()
        self.assertTrue(graph['warnings'])
        self.assertEqual(next(e for e in graph['edges'] if e['key'] == 'E03')['evidence_status'], 'UNKNOWN')
        self.assertEqual(next(e for e in graph['edges'] if e['key'] == 'E01')['consistency_checks'][0]['result'], 'MISMATCH')

    def test_edit_exposes_parent_feedback_and_actual_auxiliary_order(self):
        with patch.dict(os.environ, {'OPENAI_API_KEY': CANARY}), mock_client(self.calls):
            response = self.business.test_client().post('/api/sessions/' + self.state['id'] + '/revise/product_001', headers=HEADERS,
                data={'confirmed_revision': '1', 'card_revision': '2', 'parent_run_id': self.run,
                      'operation_id': uuid4().hex, 'feedback': '只修正瓶盖', 'auxiliary_purpose': 'product_appearance',
                      'auxiliary': (io.BytesIO(anonymous_image()), 'anonymous.png')})
        self.assertEqual(response.status_code, 200, response.json)
        graph = self.graph(run_id=response.json['run_id'])
        nodes = {n['key']: n for n in graph['nodes']}
        self.assertEqual([i['role'] for i in nodes['N07']['images']], ['current_image', 'original', 'design_reference', 'auxiliary_reference'])
        self.assertEqual(nodes['N13']['fields'][0]['value'], '只修正瓶盖')
        self.assertEqual(nodes['N14']['evidence_status'], 'OBSERVED')
        self.assertEqual(nodes['N02']['fields'][1]['value'], '商品外观修正')
        self.assertNotEqual(graph['graph_id'], self.graph(run_id=self.run)['graph_id'])

    def test_review_requires_explicit_run_event_and_failure_has_no_fake_output(self):
        response = self.business.test_client().post('/api/sessions/' + self.state['id'] + '/review/product_001', headers=HEADERS,
            json={'action': 'pass', 'confirmed_revision': 1, 'card_revision': 2, 'run_id': self.run})
        self.assertEqual(response.status_code, 200, response.json)
        graph = self.graph()
        self.assertEqual(next(n for n in graph['nodes'] if n['key'] == 'N12')['evidence_status'], 'OBSERVED')
        self.assertEqual(next(e for e in graph['edges'] if e['key'] == 'E18')['evidence_status'], 'OBSERVED')
        _, state, run, _ = make_quick_evidence(self.root, failure=True)
        graph = InspectorReader(self.root, [state['id']]).inspect(state['id'])['graph_view']
        self.assertEqual(graph['selection']['run_id'], run)
        self.assertEqual(next(n for n in graph['nodes'] if n['key'] == 'P02')['execution_status'], 'FAILED')
        self.assertEqual(next(n for n in graph['nodes'] if n['key'] == 'N11')['evidence_status'], 'MISSING')
        self.assertEqual(next(e for e in graph['edges'] if e['key'] == 'E17')['evidence_status'], 'UNKNOWN')

    def test_server_environment_notice_is_explicit_and_scoped_not_inferred_from_key(self):
        client = app.create_local_debug_app(self.root, [self.state['id']], execution_mode='MOCK').test_client()
        page = client.get('/inspector?embedded=1').get_data(as_text=True)
        self.assertIn('当前服务：MOCK', page)
        self.assertIn('不代表真实 GPT 调用', page)
        self.assertEqual(client.post('/api/inspector/tasks/' + self.state['id'], headers=HEADERS).status_code, 405)
        self.assertEqual(client.get('/api/inspector/tasks/' + '0' * 32).status_code, 404)


if __name__ == '__main__':
    unittest.main()
