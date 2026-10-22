"""Generation boundary regressions: temporary anonymous inputs, never real APIs."""

import base64
import copy
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import io
import itertools
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from file_ops import read_json, sha256, write_json_atomic
from image_workflow.generation import request as construction, service, validation


def anonymous_png(size=(24, 32), color='pink', format='PNG'):
    stream = io.BytesIO()
    Image.new('RGB', size, color).save(stream, format)
    return stream.getvalue()


class GenerationPackageTests(unittest.TestCase):
    """Import and execute against explicit adapters, with no Web/SDK fixtures."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.task = self.root / 'task'
        (self.task / 'inputs').mkdir(parents=True)
        self.card = self.task / 'generations/000003/reference_002'
        self.state = {'id': 'a' * 32, 'revision': 3, 'mode': 'product_pack',
                      'inputs': {'listing': 'Anonymous L', 'description': 'Anonymous D', 'requirements': 'Anonymous R'},
                      'product': {'appearance': 'Candidate, unverified'},
                      'references': {'reference_002': {'design': 'Only this reference'}},
                      'plans': {'reference_002': {'design': 'Only this plan'}},
                      'plan_versions': {'reference_002': 2},
                      'plan_confirmations': {'reference_002': {'source': 'per_image', 'plan_version': 2}},
                      'images': []}
        for identity, color in [('product_001', 'pink'), ('product_002', 'red'),
                                ('reference_001', 'green'), ('reference_002', 'blue')]:
            data = anonymous_png(color=color)
            relative = f'inputs/{identity}.png'
            (self.task / relative).write_bytes(data)
            self.state['images'].append({'id': identity, 'role': identity.split('_')[0], 'name': identity,
                                         'file': relative, 'sha256': sha256(data), 'mime': 'image/png'})
        self.inputs_before = {path: path.read_bytes() for path in (self.task / 'inputs').iterdir()}
        self.sources = []
        for name in ('legacy.py', 't01.py', 'quick.py'):
            path = self.root / name
            path.write_bytes(('# anonymous ' + name).encode())
            self.sources.append(path)
        self.access = service.RunAccess(
            card_folder=lambda: self.card, run_folder=lambda identity: self.card / 'runs' / identity,
            input_folder=lambda: self.task, case_id=lambda: 'case-anonymous', version_count=lambda: 0,
            read_parent=lambda identity: (anonymous_png(), {'run_id': identity, 'version': 1,
                'created_at': 'parent-created', 'confirmed_revision': 3, 'url': '/anonymous/parent'}))
        self.writes, self.requests, self.client_keys = [], [], []
        self.response_bytes = anonymous_png()
        self.response_rows = None
        self.call_error = None
        sequence = itertools.count(1)
        self.io = service.GenerationIO(
            client_factory=self.client_factory, write_json=self.write, read_json=read_json,
            safe_text=lambda text: text, now=lambda: 'fixed time',
            new_run_id=lambda: f'20261021T000000Z-{next(sequence):032x}', sdk_version=lambda name: 'offline-sdk',
            source_file=self.sources[0], t01_source_file=self.sources[1], quick_source_file=self.sources[2],
            clock=itertools.count(0, .25).__next__)
        self.prompts = construction.PromptBuilders(
            construction.build_prompt, construction.build_edit_prompt,
            lambda texts, order: 'quick-generate:' + json.dumps([texts, order], ensure_ascii=False),
            lambda texts, order, feedback: 'quick-edit:' + json.dumps([texts, order, feedback], ensure_ascii=False),
            lambda auxiliary, slot: f"auxiliary:{auxiliary['purpose']}:{slot}")
        self.defaults = {'size': '24x32', 'quality': 'low', 'output_format': 'png', 'n': 1}
        self.environment = {'OPENAI_API_KEY': 'offline-only'}

    def write(self, path, value):
        self.writes.append((path.relative_to(self.task).as_posix(), copy.deepcopy(value)))
        write_json_atomic(path, value)

    @contextmanager
    def client_factory(self, key):
        self.client_keys.append(key)
        yield SimpleNamespace(images=SimpleNamespace(edit=self.respond))

    def respond(self, **arguments):
        self.requests.append(copy.deepcopy(arguments))
        running = read_json(self.latest_folder() / 'run.json')
        self.assertEqual(running['status'], 'RUNNING')
        self.assertTrue(running['api_call_attempted'])
        if self.call_error:
            raise self.call_error
        rows = self.response_rows if self.response_rows is not None else [base64.b64encode(self.response_bytes).decode()]
        raw = {'data': [{'b64_json': row} for row in rows], 'usage': {'input_tokens': 10, 'output_tokens': 20, 'total_tokens': 30}}
        return SimpleNamespace(_request_id='req_anonymous', data=[SimpleNamespace(b64_json=row) for row in rows],
                               model_dump=lambda mode: copy.deepcopy(raw))

    def execute(self, **overrides):
        options = {'access': self.access, 'io': self.io, 'prompts': self.prompts,
                   'environment': self.environment, 'models': ('offline-image-model',), 'defaults': self.defaults,
                   'quick_sizes': ('24x32', '32x24'), 'timeout_seconds': 180.0, **overrides}
        return service.execute_generation(self.state, 'reference_002', **options)

    def latest_folder(self):
        return sorted((self.card / 'runs').iterdir())[-1]

    def test_standalone_execution_saves_request_response_and_preserves_task_inputs(self):
        state_before = copy.deepcopy(self.state)
        result = self.execute()
        folder = self.latest_folder()
        request = read_json(folder / 'request.json')
        self.assertEqual(result['status'], 'SUCCEEDED')
        self.assertEqual(result['usage'], {'input_tokens': 10, 'output_tokens': 20, 'total_tokens': 30})
        self.assertEqual(result['source_sha256'], sha256(self.sources[0].read_bytes()))
        self.assertEqual(result['t01_source_sha256'], sha256(self.sources[1].read_bytes()))
        self.assertEqual(result['plan_confirmation'], self.state['plan_confirmations']['reference_002'])
        self.assertEqual([item['id'] for item in request['image_order']], ['product_001', 'product_002', 'reference_002'])
        self.assertEqual([data for name, data, mime in self.requests[0]['image']],
                         [(self.task / image['file']).read_bytes() for image in construction.select_images(self.state, 'reference_002')])
        self.assertEqual(request['prompt'], self.requests[0]['prompt'])
        self.assertEqual(request['prompt'], (folder / 'prompt.txt').read_text())
        pointer = read_json(self.card / 'current.json')
        self.assertEqual(pointer['selected_run'], result['run_id'])
        self.assertNotIn('passed_run', pointer)
        self.assertEqual(pointer['card_revision'], 2)
        self.assertEqual(result['api_elapsed_seconds'], .25)
        self.assertEqual(self.state, state_before)
        self.assertEqual({p: p.read_bytes() for p in self.inputs_before}, self.inputs_before)

    def test_request_builders_are_pure_with_images_and_configuration_supplied(self):
        before = copy.deepcopy(self.state)
        with patch.object(Path, 'open', side_effect=AssertionError('No file I/O in builders')), \
                patch.object(os, 'getenv', side_effect=AssertionError('No environment lookup')):
            parameters = construction.parameters_for(self.state, self.defaults)
            context = construction.initial_context(self.state, 'reference_002', parameters)
            selected = construction.select_images(self.state, 'reference_002')
            images, order = [], []
            for slot, image in enumerate(selected, 1):
                data = self.inputs_before[self.task / image['file']]
                payload, identity = construction.original_input(image, data, slot)
                images.append(payload)
                order.append(identity)
            context_before = copy.deepcopy(context)
            arguments, evidence = construction.build_generation_request(
                self.state, context, order, images, 'offline-image-model', parameters, 'plan-hash', 'context-hash',
                editing=False, feedback='', auxiliary=None, prompts=self.prompts)
            self.assertEqual(context, context_before)
        self.assertEqual(arguments['image'], images)
        self.assertEqual(evidence['image_order'], order)
        self.assertIn('Only this plan', arguments['prompt'])
        self.assertEqual(self.state, before)
        self.assertEqual(self.defaults['size'], '24x32')
        self.assertEqual(self.writes, [])
        self.assertEqual(self.requests, [])

    def test_parent_and_auxiliary_edit_have_correct_roles_bytes_and_scope(self):
        auxiliary = {'data': anonymous_png(color='green'), 'file': 'inputs/auxiliary_reference.png',
                     'mime': 'image/png', 'role': 'auxiliary_reference', 'purpose': 'product_appearance'}
        self.card.mkdir(parents=True)
        write_json_atomic(self.card / 'current.json', {'selected_run': 'parent', 'passed_run': 'parent', 'card_revision': 7})
        result = self.execute(parent_run_id='parent', feedback='Only this edit', auxiliary=auxiliary,
                              access=replace(self.access, version_count=lambda: 1))
        folder = self.latest_folder()
        identities = read_json(folder / 'request.json')['image_order']
        self.assertEqual([item['role'] for item in identities],
                         ['current_image', 'product', 'product', 'reference', 'auxiliary_reference'])
        self.assertEqual(result['version'], 2)
        self.assertEqual(result['parent_run_id'], 'parent')
        self.assertEqual(result['parent_version'], 1)
        self.assertEqual(result['auxiliary_reference']['image_id'], 'reference_002')
        self.assertNotIn('data', result['auxiliary_reference'])
        self.assertEqual(self.requests[0]['image'][0][1], anonymous_png())
        self.assertEqual(self.requests[0]['image'][-1][1], auxiliary['data'])
        self.assertEqual((folder / auxiliary['file']).read_bytes(), auxiliary['data'])
        context = read_json(folder / 'plan.json')
        self.assertEqual(context['operator_feedback'], 'Only this edit')
        self.assertEqual(context['parent_image']['run_id'], 'parent')
        self.assertEqual(context['auxiliary_reference']['purpose'], 'product_appearance')
        self.assertEqual(read_json(self.card / 'current.json')['passed_run'], 'parent')
        self.assertEqual([name for name, value in self.writes].count(str((folder / 'plan.json').relative_to(self.task))), 3)

    def test_quick_path_selects_only_its_original_and_shared_style_without_plan(self):
        self.state.update(mode='quick_redesign', output_size='32x24')
        for key in ('product', 'plans', 'references'):
            self.state.pop(key)
        self.response_bytes = anonymous_png(size=(32, 24))
        result = service.execute_generation(self.state, 'product_002', access=self.access, io=self.io,
            prompts=self.prompts, environment=self.environment, models=('offline-image-model',), defaults=self.defaults,
            quick_sizes=('24x32', '32x24'), timeout_seconds=180.0)
        self.assertEqual(result['status'], 'SUCCEEDED')
        self.assertEqual([item['id'] for item in result['inputs']], ['product_002', 'reference_001', 'reference_002'])
        self.assertEqual([item['role'] for item in result['inputs']], ['original', 'design_reference', 'design_reference'])
        self.assertEqual(self.requests[0]['size'], '32x24')
        self.assertTrue(self.requests[0]['prompt'].startswith('quick-generate:'))
        self.assertNotIn('plan_version', result)
        self.assertEqual(result['plan_sha256'], result['context_sha256'])
        self.assertEqual(result['quick_redesign_source_sha256'], sha256(self.sources[2].read_bytes()))

    def test_changed_second_input_keeps_first_snapshot_and_context_before_failure(self):
        (self.task / self.state['images'][1]['file']).write_bytes(b'changed')
        result = self.execute()
        folder = self.latest_folder()
        self.assertEqual(result['status'], 'FAILED')
        self.assertFalse(result['api_call_attempted'])
        self.assertEqual((folder / self.state['images'][0]['file']).read_bytes(), anonymous_png())
        self.assertFalse((folder / self.state['images'][1]['file']).exists())
        self.assertTrue((folder / 'plan.json').is_file())
        self.assertFalse((folder / 'request.json').exists())
        self.assertEqual(self.client_keys, [])

    def test_unknown_model_and_missing_key_stop_at_original_evidence_stage(self):
        for environment, has_request in [({'OPENAI_IMAGE_MODEL': 'unsupported'}, False), ({'OPENAI_API_KEY': ''}, True)]:
            with self.subTest(environment=list(environment)):
                result = self.execute(environment=environment)
                self.assertFalse(result['api_call_attempted'])
                self.assertEqual(result['status'], 'FAILED')
                self.assertEqual((self.latest_folder() / 'request.json').exists(), has_request)
        self.assertEqual(self.client_keys, [])

    def test_client_entry_failure_and_api_failure_keep_distinct_attempt_flags(self):
        def unavailable(key):
            raise RuntimeError('offline client construction')
        first = self.execute(io=replace(self.io, client_factory=unavailable))
        self.call_error = RuntimeError('offline model transport')
        second = self.execute()
        self.assertFalse(first['api_call_attempted'])
        self.assertNotIn('api_elapsed_seconds', first)
        self.assertTrue(second['api_call_attempted'])
        self.assertEqual(second['api_elapsed_seconds'], .25)
        self.assertEqual(len(self.requests), 1)  # no automatic retry

    def test_error_and_interrupt_preserve_previous_selection_pass_and_bytes(self):
        original = self.execute()
        folder = self.latest_folder()
        original_bytes = {p: p.read_bytes() for p in folder.rglob('*') if p.is_file()}
        pointer = read_json(self.card / 'current.json')
        pointer['passed_run'] = original['run_id']
        write_json_atomic(self.card / 'current.json', pointer)
        for error in (TimeoutError('offline timeout'), KeyboardInterrupt()):
            with self.subTest(error=type(error).__name__):
                self.call_error = error
                failed = self.execute(operation_id='b' * 32)
                self.assertEqual(failed['status'], 'FAILED')
                self.assertEqual(failed['error']['type'], type(error).__name__)
                self.assertTrue(failed['api_call_attempted'])
                current = read_json(self.card / 'current.json')
                self.assertEqual(current['selected_run'], original['run_id'])
                self.assertEqual(current['passed_run'], original['run_id'])
        self.assertEqual({p: p.read_bytes() for p in original_bytes}, original_bytes)
        self.assertEqual(len(self.requests), 3)

    def test_response_shape_and_base64_failures_save_response_without_image(self):
        for rows, kind in [([], 'ValueError'), (['', ''], 'ValueError'), ([''], 'ValueError'), (['bad*'], 'Error')]:
            with self.subTest(rows=rows):
                self.response_rows = rows
                result = self.execute()
                self.assertEqual(result['error']['type'], kind)
                self.assertTrue((self.latest_folder() / 'response.json').exists())
                self.assertFalse((self.latest_folder() / 'image.png').exists())
                self.assertEqual(result['usage']['total_tokens'], 30)

    def test_invalid_image_dimensions_or_format_retain_decoded_bytes_before_failure(self):
        for data, kind in [(b'not-image', 'UnidentifiedImageError'), (anonymous_png((32, 24)), 'ValueError'),
                           (anonymous_png(format='JPEG'), 'ValueError')]:
            with self.subTest(kind=kind, bytes=len(data)):
                self.response_bytes = data
                result = self.execute()
                self.assertEqual(result['error']['type'], kind)
                self.assertFalse(result['output']['validated'])
                self.assertEqual((self.latest_folder() / 'image.png').read_bytes(), data)
                self.assertEqual(result['output']['sha256'], sha256(data))

    def test_initial_pointer_write_failure_still_propagates_without_finalization(self):
        def fail_current(path, value):
            if path.name == 'current.json':
                raise OSError('offline pointer write failure')
            self.write(path, value)
        with self.assertRaisesRegex(OSError, 'pointer write failure'):
            self.execute(io=replace(self.io, write_json=fail_current))
        record = read_json(self.latest_folder() / 'run.json')
        self.assertEqual(record['status'], 'RUNNING')
        self.assertNotIn('finished_at', record)
        self.assertFalse((self.latest_folder() / 'error.json').exists())
        self.assertEqual(self.requests, [])

    def test_import_and_execution_without_http_sdk_store_or_other_workflows(self):
        code = '''
import importlib.abc, runpy, sys, unittest
class Guard(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, *args):
        if fullname.split('.')[0] in {'flask', 'openai', 'prepare_plan', 'generate_plan_image',
                                     'image_review', 'quick_redesign', 'generate_image', 'evidence', 'persistence'}:
            raise AssertionError('Forbidden Generation dependency: ' + fullname)
sys.meta_path.insert(0, Guard())
suite = runpy.run_path(sys.argv[1])['GenerationPackageTests']
result = unittest.TextTestRunner().run(unittest.TestSuite([
    suite('test_standalone_execution_saves_request_response_and_preserves_task_inputs'),
    suite('test_request_builders_are_pure_with_images_and_configuration_supplied')]))
sys.exit(not result.wasSuccessful())
'''
        result = subprocess.run([sys.executable, '-B', '-c', code, str(Path(__file__).resolve())],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)


def compatibility_fingerprints(*, details=False):
    """Capture legacy Web execution, including partial Evidence and write order.

    Goldens were recorded on d120e41 BEFORE extracting Generation. SDK arguments
    include the actual image bytes; synthetic PNGs never contain business data.
    Dynamic IDs/times and entry hashes are normalized, not business revisions.
    """
    import httpx
    import test_generate_plan_image as fixtures
    from image_workflow.generation import auxiliary as image_review
    from cli import quick_redesign

    cases = {}
    scenarios = ('first', 'regenerate', 'edit', 'auxiliary', 'quick', 'quick_edit', 'quick_auxiliary',
                 'unknown_model', 'unknown_size', 'changed_image', 'missing_key', 'empty_response',
                 'bad_base64', 'invalid_image', 'wrong_dimensions', 'rate_limit', 'server_error',
                 'connection', 'timeout', 'interrupt', 'too_many_images')
    for scenario in scenarios:
        fx = fixtures.GenerationPageTests()
        fx.setUp()
        try:
            generation = fixtures.generation
            state = copy.deepcopy(fx.state)
            state['case_id'] = 'case-anonymous'
            previous_root = fx.store.folder(state['id'])
            state['id'] = '1' * 32
            previous_root.rename(fx.store.folder(state['id']))
            quick = scenario.startswith('quick') or scenario == 'unknown_size'
            if quick:
                state.update(mode='quick_redesign', output_size='1024x1536')
            target = 'product_002' if quick else 'reference_002'
            service = fx.app.extensions['generation_service']
            writes, requests = [], []
            root = fx.store.folder(state['id'])
            original_open, original_json = Path.open, generation.write_json

            def track_open(path, mode='r', *args, **kwargs):
                if path.is_relative_to(root) and any(flag in mode for flag in ('w', 'a', 'x', '+')):
                    writes.append(['open', str(path.relative_to(root)), mode])
                return original_open(path, mode, *args, **kwargs)

            def track_json(path, value):
                writes.append(['json', str(path.relative_to(root)), copy.deepcopy(value)])
                return original_json(path, value)

            def respond(**arguments):
                requests.append(copy.deepcopy(arguments))
                request = httpx.Request('POST', 'https://api.openai.com/v1/images/edits')
                if scenario in ('connection', 'timeout') and len(requests) == attempt:
                    error = httpx.ConnectError if scenario == 'connection' else httpx.ReadTimeout
                    raise error('offline transport failure', request=request)
                if scenario in ('rate_limit', 'server_error') and len(requests) == attempt:
                    from openai import APIStatusError
                    response = httpx.Response(429 if scenario == 'rate_limit' else 500, request=request,
                                              headers={'x-request-id': 'req_offline_failure'})
                    raise APIStatusError('offline rejection', response=response, body={'error': 'anonymous'})
                if scenario == 'interrupt' and len(requests) == attempt:
                    raise KeyboardInterrupt()
                data = fixtures.png((1024, 1536))
                if scenario == 'invalid_image':
                    data = b'not an image'
                if scenario == 'wrong_dimensions':
                    data = fixtures.png((24, 32))
                encoded = 'invalid*base64' if scenario == 'bad_base64' else base64.b64encode(data).decode()
                rows = [] if scenario == 'empty_response' else [SimpleNamespace(b64_json=encoded)]
                raw = {'created': 1, 'data': [{'b64_json': item.b64_json} for item in rows],
                       'usage': {'input_tokens': 10, 'output_tokens': 20, 'total_tokens': 30}}
                return SimpleNamespace(_request_id='req_offline_generation', data=rows,
                                       model_dump=lambda mode: copy.deepcopy(raw))

            @contextmanager
            def client_factory(key):
                yield SimpleNamespace(images=SimpleNamespace(edit=respond))

            has_parent = scenario in ('edit', 'auxiliary', 'quick_edit', 'quick_auxiliary', 'too_many_images')
            has_previous = has_parent or scenario == 'regenerate'
            attempt = 2 if has_previous else 1
            sequence = itertools.count(1)
            with patch.object(generation, 'make_client', side_effect=client_factory), \
                    patch.object(generation, 'datetime', SimpleNamespace(now=lambda tz: datetime(2026, 10, 21, tzinfo=timezone.utc))), \
                    patch.object(generation, 'uuid4', side_effect=lambda: SimpleNamespace(hex=f'{next(sequence):032x}')), \
                    patch.object(generation, 'now', return_value='2026-10-21T00:00:00+00:00'), \
                    patch.object(generation, 'time', SimpleNamespace(perf_counter=lambda: 1.0)), \
                    patch.object(generation, 'version', return_value='offline-sdk'), \
                    patch.object(generation, 'write_json', side_effect=track_json), \
                    patch.object(Path, 'open', track_open):
                parent = service._generate(state, target) if has_previous else None
                task = service.folder(state['id'], state['revision'], target)
                if parent:
                    # Accept V1, then verify every subsequent path preserves it.
                    pointer = generation.read_json(task / 'current.json')
                    pointer.update(passed_run=parent['run_id'], passed_at='fixed acceptance')
                    original_json(task / 'current.json', pointer)
                environment = {}
                if scenario == 'unknown_model':
                    environment['OPENAI_IMAGE_MODEL'] = 'unsupported-offline'
                if scenario == 'unknown_size':
                    state['output_size'] = 'invalid-size'
                if scenario == 'missing_key':
                    environment['OPENAI_API_KEY'] = ''
                if scenario == 'changed_image':
                    (root / state['images'][1]['file']).write_bytes(b'changed anonymous input')
                if scenario == 'too_many_images':
                    for index in range(3, 16):
                        identity = f'product_{index:03}'
                        path = root / f'inputs/{identity}.png'
                        path.write_bytes(fixtures.png())
                        state['images'].append({'id': identity, 'role': 'product', 'name': identity + '.png',
                                                'file': str(path.relative_to(root)), 'mime': 'image/png',
                                                'sha256': generation.sha256(path.read_bytes())})
                auxiliary = None
                if scenario in ('auxiliary', 'quick_auxiliary', 'too_many_images'):
                    auxiliary = image_review.prepare_auxiliary('new.png', fixtures.png(), 'product_appearance')
                with patch.dict(os.environ, environment):
                    record = service._generate(state, target, parent['run_id'] if has_parent else None,
                                               'Only current image' if has_parent else '', 'f' * 32, auxiliary)
            assert record['status'] == ('SUCCEEDED' if scenario in ('first', 'regenerate', 'edit', 'auxiliary',
                                                                 'quick', 'quick_edit', 'quick_auxiliary') else 'FAILED'), record
            pointer = generation.read_json(task / 'current.json')
            if parent:
                assert pointer['passed_run'] == parent['run_id']
            expected_calls = attempt if scenario not in ('unknown_model', 'unknown_size', 'changed_image',
                                                         'missing_key', 'too_many_images') else attempt - 1
            assert len(requests) == expected_calls, (scenario, len(requests))
            assert record['source_sha256'] == generation.sha256(Path(generation.__file__).read_bytes())
            assert record['t01_source_sha256'] == generation.sha256((Path(generation.__file__).resolve().parents[2] / 'cli/generate_image.py').read_bytes())
            if 'quick_redesign_source_sha256' in record:
                assert record['quick_redesign_source_sha256'] == generation.sha256(Path(quick_redesign.__file__).read_bytes())
            files = {str(path.relative_to(task)): path.read_bytes() for path in sorted(task.rglob('*')) if path.is_file()}

            def encode(value):
                if isinstance(value, bytes):
                    return {'bytes_b64': base64.b64encode(value).decode()}
                raise TypeError(type(value).__name__)

            # Decode JSON/text bytes for normalization, preserve binary bytes exactly.
            for name, data in list(files.items()):
                if name.endswith(('.json', '.txt', '.md')):
                    files[name] = data.decode('utf-8')
            payload = json.dumps({'record': record, 'requests': requests, 'writes': writes,
                                  'files': files}, ensure_ascii=False, sort_keys=True, default=encode)
            payload = payload.replace(state['id'], '<TASK>')
            run_ids = list(dict.fromkeys(re.findall(r'\d{8}T\d{6}Z-[0-9a-f]{32}', payload)))
            for index, identity in enumerate(run_ids):
                payload = payload.replace(identity, f'<RUN{index}>')
            for path, label in ((Path(generation.__file__), 'generate_plan_image.py'),
                                (Path(generation.__file__).resolve().parents[2] / 'cli/generate_image.py', 'generate_image.py'),
                                (Path(quick_redesign.__file__), 'quick_redesign.py')):
                payload = payload.replace(generation.sha256(path.read_bytes()), '<ENTRY_HASH:' + label + '>')
            payload = re.sub(r'0x[0-9a-f]+', '<MEMORY_ADDRESS>', payload)
            cases[scenario] = json.loads(payload) if details else hashlib.sha256(payload.encode()).hexdigest()
        finally:
            fx.tearDown()
            fx.doCleanups()
    return cases


class GenerationCompatibilityTests(unittest.TestCase):
    def test_legacy_requests_evidence_state_and_write_order_match(self):
        self.assertEqual(compatibility_fingerprints(), LEGACY_GOLDEN)


LEGACY_GOLDEN = {
    'first': 'd99e105be2bb215e9c450a008a98aa85a5daf7840ffac89a1df971422a2d5125',
    'regenerate': 'd6109071e45ff132301d51486b35b4e851aa84f23da6231a43b676b6074ab6c8',
    'edit': '413c56ffa9c125307aead6cc2ed067491f88783dcae605daf820cd0aa78a883e',
    'auxiliary': 'c35d6756caed51d4fbbec0b29fc2e25fc21ba7700598abdeaabcfd54b395c687',
    'quick': 'cf01cf177f13ab450de9c9dafe941765eaf04cb5643058f3ebc8ea800c79bacb',
    'quick_edit': 'd8cf6bdbb61cf5a286e8b68615324fab9d44c993573041072934ba0126cd727c',
    'quick_auxiliary': 'a5fdfe30fff639f827c7619eb831731c7ad2cbc9a2a5f64b077929da7a3a48ed',
    'unknown_model': '0c6a7742f63d872ab31cd2aca48c990c9517dd458655c79a0741ea6546c0318f',
    'unknown_size': 'ab9f4f7065886508f375f102efe138d6049c449318070530f11ea2bf8375781a',
    'changed_image': 'cd20dcdcd99073c8bd5638988074aa5af1538b0057dd59d3064d2ac23ce8a8cb',
    'missing_key': '4180d22f11303b2b298def9880216f196765133da413d9fa2b460e40bab902fa',
    'empty_response': '63f0684ec5c317ac58eda9e0d281f899d9a8c95ac270294db931fcf5041164ae',
    'bad_base64': '8a228de66c76461692eb8b43a440824d7bac15efabd2c827d6e53520dbc8a10d',
    'invalid_image': '50517fadc4843acda0921583b8dad4d998562e1787e771b7e044f0242753dae0',
    'wrong_dimensions': 'f80ccd7c6a1e6be5e7a1acd48f89ad5fe065489b1343aa543c4f55b9df6c02bb',
    'rate_limit': '60725dee6d6eea7787eaec12d78eda9bc656cc729f8aa29564c619a8cf0b97a7',
    'server_error': 'f52655d75fe5da79043b3b8a503effee6fabbc0c4c0e43932a504eaae59f7500',
    'connection': 'a23847b2bdbe8198189ca38f3cbe1920f39156fe9595b9307a2faf0ff6488215',
    'timeout': 'a6e4d4c1b4347703dc637c2a6b3f45fcba52bf0f0ce0e0bdbd8c515cb8a92c94',
    'interrupt': 'd72a8568179fc53c04fc87eebba4b8c86ad452a777d776a90762059ec72264b9',
    'too_many_images': '2341693a404f0bb5e0b307a3ad7ffe481f3a6a7de387cce38d005cf1e4ec0ee6',
}


if __name__ == '__main__':
    unittest.main()
