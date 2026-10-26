"""Execute one Web image Run, preserving progressive Evidence and failures.

Confirmation, locks, operation deduplication and review remain caller-owned.
Only scoped, read-only parent/version access is supplied by that boundary;
this package never calls Review/Store/Flask or decides a human Pass.
"""

import copy
from dataclasses import dataclass
import json
from pathlib import Path
import time
from typing import Callable, Mapping

from file_ops import safe_path, sha256
from .request import (PromptBuilders, build_generation_request, initial_context,
                      original_input, parameters_for, parent_input, redesign_order, select_images)
from .validation import decode_response, validate_image
import image_workflow.generation.quick_v1 as quick_v1


@dataclass(frozen=True)
class RunAccess:
    """Scoped paths and read-only version queries, not an entire Web service."""

    card_folder: Callable
    run_folder: Callable
    input_folder: Callable
    case_id: Callable
    version_count: Callable
    read_parent: Callable


@dataclass(frozen=True)
class GenerationIO:
    """Per-call execution adapters preserving existing storage/redaction policy.

    source_file is the supplied calling entry, NOT this package or all
    its dependencies. The existing source_sha256 field keeps that limited scope.
    """

    client_factory: Callable
    write_json: Callable
    read_json: Callable
    safe_text: Callable
    now: Callable
    new_run_id: Callable
    sdk_version: Callable
    source_file: Path
    t01_source_file: Path
    quick_source_file: Path
    clock: Callable = time.perf_counter


def prepare_context(folder, state, target, parameters, record, io):
    """Snapshot initial Context/text before loading images, as in the old Run."""
    quick = state.get('mode') == 'quick_redesign'
    context = initial_context(state, target, parameters)
    if quick:
        if quick_v1.is_v1(state):
            record.update(quick_business_version=quick_v1.VERSION, output_id=target,
                          output_slot=copy.deepcopy(context['output_slot']))
        else:
            record['source_image_id'] = target
        record['quick_redesign_source_sha256'] = sha256(io.quick_source_file.read_bytes())
    io.write_json(folder / 'plan.json', context)
    record['plan_sha256'] = sha256(json.dumps(context if quick else state['plans'][target],
                                             ensure_ascii=False, sort_keys=True).encode())
    if quick:
        record['context_sha256'] = record['plan_sha256']
    for name, text in state['inputs'].items():
        if name in ['listing', 'description', 'requirements', 'product_facts']:
            (folder / 'inputs' / f'{name}.md').write_text(io.safe_text(text), encoding='utf-8')
    return context


def prepare_images(folder, state, target, context, record, parent_run_id, feedback, auxiliary, access, io):
    """Read/hash/copy one input at a time, preserving partial failure artifacts.

    Context is deliberately persisted before parent data, after the parent and
    after auxiliary metadata. Preloading all images would change error Evidence.
    """
    selected = select_images(state, target)
    images, order = [], []
    if parent_run_id:
        data, parent = access.read_parent(parent_run_id)
        with (folder / 'inputs/current_image.png').open('xb') as stream:
            stream.write(data)
        context, image, identity = parent_input(context, data, parent, feedback)
        images.append(image)
        order.append(identity)
        io.write_json(folder / 'plan.json', context)
        record['parent_version'] = parent['version']
    for image in selected:
        data = (access.input_folder() / image['file']).read_bytes()
        if sha256(data) != image['sha256']:
            raise ValueError('保存的输入图片发生变化，已停止调用。')
        name = Path(image['file']).name
        with (folder / 'inputs' / name).open('xb') as stream:
            stream.write(data)
        payload, identity = original_input(image, data, len(order) + 1)
        images.append(payload)
        order.append(identity)
    if quick_v1.is_v1(state):
        for item in order:
            if item['role'] == 'reference':
                item['role'] = 'design_reference'
    elif state.get('mode') == 'quick_redesign':
        order = redesign_order(order, target)
    if auxiliary:
        metadata = record['auxiliary_reference']
        images.append((Path(auxiliary['file']).name, auxiliary['data'], auxiliary['mime']))
        order.append({**metadata, 'id': 'auxiliary_reference', 'slot': len(order) + 1})
        context['auxiliary_reference'] = metadata
        io.write_json(folder / 'plan.json', context)
    return context, images, order


def save_request(folder, arguments, evidence, record, io):
    (folder / 'prompt.txt').write_text(io.safe_text(arguments['prompt']), encoding='utf-8')
    io.write_json(folder / 'request.json', evidence)
    record['inputs'] = evidence['image_order']
    record['prompt_sha256'] = sha256(arguments['prompt'].encode())


def invoke_model(arguments, api_key, record, folder, io):
    """Exactly one Images Edit SDK attempt; existing client owns timeout/retries."""
    if not api_key.strip():
        raise ValueError('图像服务尚未配置。请在启动服务的终端设置环境密钥；本次没有调用模型。')
    with io.client_factory(api_key) as client:
        record['api_call_attempted'] = True
        record['api_started_at'] = io.now()
        io.write_json(folder / 'run.json', record)
        api_started = io.clock()
        try:
            response = client.images.edit(**arguments)
        finally:
            record['api_elapsed_seconds'] = round(io.clock() - api_started, 3)
    return response


def receive_image(response, parameters, record, folder, io):
    """Save actual response and decoded bytes BEFORE technical validation."""
    record['request_id'] = response._request_id
    raw = response.model_dump(mode='json')
    record['usage'] = raw.get('usage')
    io.write_json(folder / 'response.json', raw)
    data = decode_response(response)
    with (folder / 'image.png').open('xb') as stream:
        stream.write(data)
    record['output'] = {'file': 'image.png', 'bytes': len(data), 'sha256': sha256(data), 'validated': False}
    validate_image(data, parameters['size'])
    record['output']['validated'] = True


def execute_generation(state, target, parent_run_id=None, feedback='', operation_id=None, auxiliary=None, *,
                       access: RunAccess, io: GenerationIO, prompts: PromptBuilders, environment: Mapping,
                       models: tuple, defaults: Mapping, quick_sizes: tuple, timeout_seconds):
    """Return a technical Run record; leave Task state/locks/Pass untouched.

    Paths and identities are validated by the compatibility/application boundary.
    Initial Run/current writes intentionally remain outside the try/finally:
    preserving that old failure window is part of this structural migration.
    """
    started = io.clock()
    revision = state['revision']
    task_folder = access.card_folder()
    run_id = io.new_run_id()
    folder = access.run_folder(run_id)
    (folder / 'inputs').mkdir(parents=True, exist_ok=False)
    old_pointer = io.read_json(task_folder / 'current.json') if (task_folder / 'current.json').is_file() else {}
    pointer = {**old_pointer, 'latest_run': run_id, 'last_successful_run': old_pointer.get('last_successful_run'),
               'card_revision': old_pointer.get('card_revision', 0) + 1}
    model = environment.get('OPENAI_IMAGE_MODEL', models[0])
    quick = state.get('mode') == 'quick_redesign'
    parameters = parameters_for(state, defaults, target)
    record = {
        'run_id': run_id, 'session_id': state['id'], 'reference_id': target, 'confirmed_revision': revision,
        'case_id': access.case_id(), 'action': 'revise_image' if parent_run_id else 'generate_image',
        'parent_run_id': parent_run_id, 'feedback': feedback, 'operation_id': operation_id,
        'version': access.version_count() + 1,
        'confirmed_version_file': f'versions/{revision:06}.json', 'mode': state.get('mode', 'product_pack'),
        'started_at': io.now(), 'status': 'RUNNING', 'model': model, 'parameters': parameters,
        'sdk_version': io.sdk_version('openai'), 'source_sha256': sha256(io.source_file.read_bytes()),
        't01_source_sha256': sha256(io.t01_source_file.read_bytes()),
        'endpoint': 'https://api.openai.com/v1/images/edits', 'max_retries': 0, 'timeout_seconds': timeout_seconds,
        'api_call_attempted': False, 'request_id': None, 'usage': None, 'output': None, 'error': None,
    }
    if not quick:
        record['plan_version'] = state.get('plan_versions', {}).get(target)
        record['plan_confirmation'] = copy.deepcopy(state.get('plan_confirmations', {}).get(target))
        record['plan_confirmation_source'] = (record['plan_confirmation'] or {}).get('source', 'LEGACY_GLOBAL_CONFIRMED')
    if auxiliary:
        record['auxiliary_reference'] = {key: value for key, value in auxiliary.items() if key != 'data'}
        record['auxiliary_reference'].update(session_id=state['id'], image_id=target, parent_run_id=parent_run_id)
    io.write_json(folder / 'run.json', record)
    io.write_json(task_folder / 'current.json', pointer)
    try:
        if auxiliary:
            with safe_path(folder, auxiliary['file']).open('xb') as stream:
                stream.write(auxiliary['data'])
        if model not in models:
            raise ValueError('图像模型配置不在 T01 已核实的模型列表内。')
        if quick and parameters['size'] not in quick_sizes:
            raise ValueError('重设计输出比例无效，未调用模型。')
        context = prepare_context(folder, state, target, parameters, record, io)
        context, images, order = prepare_images(folder, state, target, context, record, parent_run_id,
                                                feedback, auxiliary, access, io)
        record['context_sha256'] = sha256(json.dumps(context, ensure_ascii=False, sort_keys=True).encode())
        if quick:
            record['plan_sha256'] = record['context_sha256']
        arguments, evidence = build_generation_request(state, context, order, images, model, parameters,
            record['plan_sha256'], record['context_sha256'], editing=bool(parent_run_id), feedback=feedback,
            auxiliary=auxiliary, prompts=prompts)
        save_request(folder, arguments, evidence, record, io)
        response = invoke_model(arguments, environment.get('OPENAI_API_KEY', ''), record, folder, io)
        receive_image(response, parameters, record, folder, io)
        record['image_created_at'] = io.now()
        record['status'] = 'SUCCEEDED'
        pointer['last_successful_run'] = run_id
        pointer['selected_run'] = run_id
    except (Exception, KeyboardInterrupt) as error:
        record['status'] = 'FAILED'
        record['request_id'] = getattr(error, 'request_id', None) or record['request_id']
        record['error'] = {'type': type(error).__name__, 'message': str(error),
                           'status_code': getattr(error, 'status_code', None), 'body': getattr(error, 'body', None)}
        io.write_json(folder / 'error.json', record['error'])
    finally:
        record['finished_at'] = io.now()
        record['elapsed_seconds'] = round(io.clock() - started, 3)
        pointer['card_revision'] += 1
        io.write_json(folder / 'run.json', record)
        io.write_json(task_folder / 'current.json', pointer)
    return record
