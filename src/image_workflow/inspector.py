"""Read-only, task-allowlisted projections of saved workflow Evidence.

No model client, business transitions, repair, export or persistence writes.
Links inferred from Task events are explicitly distinct from original files.
"""

import io
import json
from pathlib import Path
import re

from PIL import Image

from file_ops import read_json, safe_path, sha256
from infrastructure.evidence import clean_record, contains_private
from image_workflow.inspector_graph import context_graph
from persistence import task_state


TASK_ID = re.compile(r'[0-9a-f]{32}')
IMAGE_ID = re.compile(r'(?:product|reference)_[0-9]+')
RUN_ID = re.compile(r'[0-9]{8}T[0-9]{6}Z-[0-9a-f]{32}')
IMAGE_FILE = re.compile(r'inputs/(?:(?:product|reference)_[0-9]+\.(?:jpg|jpeg|png|webp)|current_image\.png|auxiliary_reference\.(?:jpg|png|webp))')
MAX_DOCUMENT_BYTES = 48 * 1024 * 1024
MAX_IMAGE_BYTES = 24 * 1024 * 1024


class InspectorError(ValueError):
    pass


def preview(value):
    """Hide image encodings before applying the existing credential/reasoning filter."""
    if isinstance(value, dict):
        return clean_record({key: ('[图片编码已省略；使用受限图片预览]' if key == 'b64_json' else preview(item))
                             for key, item in value.items()})
    if isinstance(value, list):
        return clean_record([preview(item) for item in value])
    if isinstance(value, str):
        if value.startswith('data:image/'):
            return '[图片 data URL 已省略；原文件哈希保留]'
        return clean_record(value)
    return value


def context_view(selection, mode, nodes, assets):
    """Project the SAME parsed documents into a Quick Run view; no I/O or policy rebuild.

    A saved Context is not the SDK request. Presence checks compare only saved
    strings and hashes, never today's Prompt builder or an LLM interpretation.
    """
    if mode != 'quick_redesign':
        return {'supported': False, 'note': 'V0.6 仅解释 Quick Redesign；商品图包请查看原有执行节点。', 'cards': []}
    documents = {(node['id'], doc['key']): doc for node in nodes for doc in node['documents']}

    def doc(key, node='generation'):
        return documents.get((node, key), {})

    def source(key, pointer='', node='generation'):
        item = doc(key, node)
        return {'node_id': node, 'document_key': key, 'file': item.get('file', key),
                'pointer': pointer, 'sha256': item.get('sha256'), 'status': item.get('status', 'MISSING')}

    def value(key, path=(), node='generation'):
        item = doc(key, node)
        result = item.get('data') if item.get('status') == 'OBSERVED' else None
        for part in path:
            if not isinstance(result, dict) or part not in result:
                return None
            result = result[part]
        return result

    def field(label, key, path=(), node='generation', note=''):
        result = value(key, path, node)
        pointer = ''.join('/' + str(part).replace('~', '~0').replace('/', '~1') for part in path)
        return {'label': label, 'value': result, 'status': 'OBSERVED' if result is not None else 'UNKNOWN',
                'sources': [source(key, pointer, node)], 'note': note}

    def check(label, result, sources, note=''):
        return {'label': label, 'result': result, 'sources': sources, 'note': note}

    def card(identity, title, summary, fields=(), images=(), checks=(), note=''):
        observed = any(item['status'] == 'OBSERVED' for item in fields) or any(item['status'] == 'OBSERVED' for item in images)
        return {'id': identity, 'title': title, 'summary': summary, 'status': 'OBSERVED' if observed else 'UNKNOWN',
                'fields': list(fields), 'images': list(images), 'checks': list(checks), 'note': note}

    context = value('plan.json')
    context_matches = (isinstance(context, dict) and context.get('session_id') == selection['task_id'] and
                       context.get('mode') == 'quick_redesign' and context.get('source_image_id') == selection['image_id'] and
                       context.get('input_revision') == selection['revision'])
    warnings = []
    if isinstance(context, dict) and not context_matches:
        warnings.append('plan.json 的 Task/Image/输入 revision 不完整或不一致；不能将其认定为本次 Context。')

    def context_field(label, path, note=''):
        item = field(label, 'plan.json', path, note=note)
        if not context_matches:
            item.update(value=None, status='UNKNOWN', note='本次 Context 来源身份未确认；未用当前任务资料补写。')
        return item

    request_order = value('request.json', ('image_order',))
    order = request_order if isinstance(request_order, list) else value('run.json', ('inputs',))
    order = order if isinstance(order, list) else []
    order_key, order_path = ('request.json', '/image_order') if isinstance(request_order, list) else ('run.json', '/inputs')
    image_inputs = []
    for index, item in enumerate(order):
        asset = next((asset for asset in assets if asset['key'] == f'run-input-{index}'), {})
        image_inputs.append({'asset_key': asset.get('key'), 'id': item.get('id'), 'role': item.get('role') or 'UNKNOWN',
            'position': index + 1, 'slot': item.get('slot'), 'file': item.get('file'),
            'status': asset.get('status', 'MISSING'), 'sha256': asset.get('sha256'),
            'expected_sha256': item.get('sha256'), 'hash_matches': asset.get('hash_matches'),
            'sources': [source(order_key, order_path + '/' + str(index))],
            'note': '' if isinstance(request_order, list) else '仅 Run.inputs 留存；原 request.json 图片清单 UNKNOWN。'})
    original = [item for item in image_inputs if item['role'] in ('original', 'product') and item['id'] == selection['image_id']]
    if not original:
        # Snapshot assets may be viewed, but are NOT silently promoted to actual inputs.
        for asset in assets:
            if asset['key'].startswith('original-') and asset['label'] == selection['image_id']:
                original.append({**asset, 'asset_key': asset['key'], 'id': asset['label'],
                    'sources': [source('snapshot', '/images', 'confirmation')],
                    'note': '任务资料图片；缺少本次图片清单，是否实际发送 UNKNOWN。'})
    references = [item for item in image_inputs if item not in original]
    output = next((asset for asset in assets if asset['key'] == 'output'), None)
    outputs = [{**output, 'asset_key': 'output', 'sources': [source('run.json', '/output')]}] if output else []

    requirements = context_field('本次整体设计要求', ('original_inputs', 'requirements'))
    facts = context_field('运营提供的商品事实约束', ('original_inputs', 'product_facts'), '这是来源陈述，不等于系统核实的商品事实。')
    feedback = field('本次修改意见', 'run.json', ('feedback',))
    actual_prompt = value('request.json', ('prompt',))
    prompt = field('已保存的实际请求 Prompt', 'request.json', ('prompt',), note='展示已脱敏；是请求留存，不是模型内部处理或接收证明。')
    prompt_file = field('prompt.txt 留存全文', 'prompt.txt')
    checks = []
    for item, tag in ((requirements, 'operator_design_requirements'), (facts, 'product_constraints_from_operator'),
                      (feedback, 'revision_feedback')):
        # Exact tag/value equality, not substring coincidence elsewhere in the Prompt.
        segments = re.findall(r'<' + tag + r'>\n?(.*?)\n?</' + tag + '>', actual_prompt, re.S) if isinstance(actual_prompt, str) else []
        known = item['status'] == 'OBSERVED' and isinstance(item['value'], str) and item['value'] != ''
        result = ('MATCH' if len(segments) == 1 and segments[0] == item['value'] else 'MISMATCH') if known and isinstance(actual_prompt, str) else 'UNKNOWN'
        checks.append(check(item['label'] + ' → 请求标签', result, item['sources'] + [source('request.json', '/prompt')],
                            '只核对已保存文字；空值、历史标签缺失或缺少请求时不重建默认内容。'))
    same_prompt = (actual_prompt == prompt_file['value']) if isinstance(actual_prompt, str) and isinstance(prompt_file['value'], str) else None
    checks.append(check('request.prompt 与 prompt.txt', 'UNKNOWN' if same_prompt is None else 'MATCH' if same_prompt else 'MISMATCH',
                        prompt['sources'] + prompt_file['sources']))
    expected_prompt = value('run.json', ('prompt_sha256',))
    prompt_digest = doc('prompt.txt').get('sha256')
    checks.append(check('Prompt 文件与 Run 记录哈希', 'UNKNOWN' if not expected_prompt or not prompt_digest else 'MATCH' if expected_prompt == prompt_digest else 'MISMATCH',
                        [source('run.json', '/prompt_sha256'), source('prompt.txt')], '原文件哈希；脱敏也可能影响字节，差异不是模型根因结论。'))
    run_order = value('run.json', ('inputs',))
    checks.append(check('request.image_order 与 Run.inputs', 'UNKNOWN' if not isinstance(request_order, list) or not isinstance(run_order, list) else 'MATCH' if request_order == run_order else 'MISMATCH',
                        [source('request.json', '/image_order'), source('run.json', '/inputs')]))
    checks.append(check('输入图片记录哈希与本次文件', 'MISMATCH' if any(item['hash_matches'] is False for item in image_inputs) else
                        'MATCH' if image_inputs and all(item['hash_matches'] is True for item in image_inputs) else 'UNKNOWN',
                        [source(order_key, order_path)], '哈希只能证明字节一致，不能证明 SKU 身份正确。'))
    if any(item['slot'] != item['position'] for item in image_inputs):
        warnings.append('图片清单的数组顺序与 slot 标号不一致；按保存数组原序显示，没有自动重新排序。')
    role_lines = '\n'.join(line for line in actual_prompt.splitlines() if
        any(word in line for word in ('design_reference', '后续设计参考图', '唯一待重设计', '图片 2 是', '本次新增辅助输入', '仅影响当前图片'))
        ) if isinstance(actual_prompt, str) else None
    boundaries = {'label': '请求中可定位的图片用途与边界原文', 'value': role_lines or None,
                  'status': 'OBSERVED' if role_lines else 'UNKNOWN', 'sources': [source('request.json', '/prompt')],
                  'note': '从本次保存 Prompt 摘录；未找到已识别片段不代表不存在其他表达，也不证明模型遵守。'}
    model = field('模型', 'request.json', ('model',))
    parameter_fields = [field(label, 'request.json', (key,)) for key, label in
                        [('n', '张数'), ('quality', '质量参数'), ('size', '尺寸'), ('output_format', '格式')]]
    ids = [field(label, 'run.json', (key,)) for key, label in
           [('run_id', 'Run ID'), ('operation_id', 'Operation ID'), ('parent_run_id', '父版本 Run'),
            ('request_id', 'OpenAI request_id'), ('api_call_attempted', 'SDK 调用尝试标记')]]
    image_summary = str(len(image_inputs)) + ' 张请求图片记录' if isinstance(request_order, list) else '实际清单 UNKNOWN · ' + str(len(image_inputs)) + ' 张 Run 图片记录'
    summary = (str(model['value'] or '模型 UNKNOWN') + ' · ' + str(value('request.json', ('size',)) or '尺寸 UNKNOWN') + ' · ' + image_summary)
    request_fields = [model, *parameter_fields, *ids]
    # Run settings are displayed as Run settings, not used to fabricate request.json.
    request_fields += [field('记录的超时秒数', 'run.json', ('timeout_seconds',)), field('记录的重试上限', 'run.json', ('max_retries',))]
    cards = [
        card('product', 'Product Input · 商品依据', str(len(original)) + ' 张本图商品依据',
             [field('输入快照 revision', 'snapshot', ('revision',), 'confirmation'),
              field('快照中的商品描述', 'snapshot', ('inputs', 'description'), 'confirmation', '保存在资料快照中不代表此字段原样发送到 Quick Prompt。'),
              field('快照中的 Listing', 'snapshot', ('inputs', 'listing'), 'confirmation', 'Quick 不强制 Listing；不将该字段自动认定为 Prompt 内容。'),
              field('快照中的商品事实来源', 'snapshot', ('inputs', 'product_facts'), 'confirmation', '来源陈述，不代表已核实或已进入请求；请求核对见 Context Assembly。')], original),
        card('references', 'Reference Inputs · 图片角色', str(len(references)) + ' 张参考 / 当前版本 / 辅助输入' if order else '图片清单 UNKNOWN；未从当前任务推定实际参考输入',
             [boundaries, context_field('辅助图片用途', ('auxiliary_reference', 'purpose_label')),
              context_field('辅助图片作用范围', ('auxiliary_reference', 'scope'))], references,
             note='角色来自本次图片清单；用途是运营声明，不自动确认同 SKU 或商品事实。'),
        card('requirements', 'Task Requirements · 本次要求', '整体要求、商品约束与本次修改分别保留',
             [requirements, facts, feedback]),
        card('assembly', 'Context Assembly · 组装核对', '资料快照 ≠ 整份已发送 Context',
             [context_field('Context Task', ('session_id',)), context_field('Context Image', ('source_image_id',)),
              context_field('Context 输入 revision', ('input_revision',))], checks=checks,
             note='只检查保存的 Context、Prompt、清单与字节；不调用当前 Prompt 构建器重建历史。'),
        card('request', 'Actual Model Request · 实际请求', summary, request_fields, image_inputs,
             note='按 request.image_order 数组原序展示；缺失时仅展示 Run.inputs，实际请求内容 UNKNOWN。'),
        card('output', 'Model Output · 输出对照', str(value('run.json', ('status',)) or 'UNKNOWN') + ' · 技术状态不等于人工接受',
             [field('执行状态', 'run.json', ('status',)), field('耗时（秒）', 'run.json', ('elapsed_seconds',)),
              field('API 耗时（秒）', 'run.json', ('api_elapsed_seconds',)), field('错误类型', 'error.json', ('type',)),
              field('错误信息', 'error.json', ('message',))], outputs)
    ]
    return {'supported': True, 'schema_version': 1, 'cards': cards, 'prompt': prompt, 'prompt_file': prompt_file,
            'comparison': {'before': original[0]['asset_key'] if original else None, 'after': 'output' if output else None},
            'warnings': warnings, 'note': '只读 Quick Run 投影；UNKNOWN 不使用今天的状态或代码补写。'}


class InspectorReader:
    def __init__(self, root, allowed_tasks, *, allow_runtime_tasks=False):
        self.root = Path(root).absolute()
        self.allowed = tuple(dict.fromkeys(allowed_tasks))
        self.allow_runtime_tasks = allow_runtime_tasks
        if ((not self.allowed and not allow_runtime_tasks) or
                any(not TASK_ID.fullmatch(identity) for identity in self.allowed)):
            raise InspectorError('必须显式指定至少一个有效的获准 Task ID。')

    def allows_task(self, identity):
        """Live scope is an existing task inside this root, never a browser grant."""
        if not self.allow_runtime_tasks:
            return identity in self.allowed
        if not isinstance(identity, str) or not TASK_ID.fullmatch(identity):
            return False
        try:
            folder = safe_path(self.root, 'sessions/' + identity)
            state = task_state.read_current(folder, reader=self._read_json)
            return isinstance(state, dict) and state.get('id') == identity
        except (OSError, ValueError, TypeError, RecursionError):
            return False

    def folder(self, identity):
        if not self.allows_task(identity):
            raise InspectorError('任务不在本次授权范围内。')
        return safe_path(self.root, 'sessions/' + identity)

    def _read_json(self, path):
        if path.stat().st_size > MAX_DOCUMENT_BYTES:
            raise InspectorError('证据文件超过本地查看上限。')
        return read_json(path)

    def state(self, identity):
        state = task_state.read_current(self.folder(identity), reader=self._read_json)
        if not isinstance(state, dict) or state.get('id') != identity:
            raise InspectorError('任务身份与保存记录不一致。')
        return state

    def tasks(self):
        rows = []
        identities = self.allowed
        if self.allow_runtime_tasks:
            sessions = safe_path(self.root, 'sessions')
            identities = [child.name for child in sorted(sessions.iterdir())
                          if self.allows_task(child.name)] if sessions.is_dir() else []
        for identity in identities:
            try:
                state = self.state(identity)
                rows.append({'id': identity, 'title': state.get('title', identity), 'status': 'OBSERVED'})
            except (OSError, ValueError, KeyError):
                rows.append({'id': identity, 'title': '授权任务缺失或不可读取', 'status': 'MISSING'})
        return preview(rows)

    def document(self, root, relative, key):
        path = safe_path(root, relative)
        result = {'key': key, 'file': relative, 'status': 'MISSING', 'data': None}
        if not path.is_file():
            result['note'] = '原始文件不存在；未从当前状态重建。'
            return result
        if path.stat().st_size > MAX_DOCUMENT_BYTES:
            result['note'] = '文件超过查看上限，未加载。'
            return result
        raw = path.read_bytes()
        result.update(sha256=sha256(raw), bytes=len(raw))
        try:
            result['data'] = preview(json.loads(raw) if path.suffix == '.json' else raw.decode('utf-8'))
            result['status'] = 'OBSERVED'
        except (ValueError, UnicodeError, RecursionError):
            result['note'] = '原始文件无法解析；保留文件身份与字节哈希。'
        return result

    def _directories(self, root, relative, pattern):
        folder = safe_path(root, relative)
        return [child.name for child in sorted(folder.iterdir())
                if pattern.fullmatch(child.name) and safe_path(folder, child.name).is_dir()] if folder.is_dir() else []

    def _asset(self, root, relative, key, label, role, expected=None):
        # The browser only receives opaque keys, never a file-path parameter.
        path = safe_path(root, relative)
        asset = {'key': key, 'label': label, 'role': role, 'file': relative, 'status': 'MISSING',
                 'expected_sha256': expected}
        if path.is_file() and path.stat().st_size <= MAX_IMAGE_BYTES:
            data = path.read_bytes()
            actual = sha256(data)
            asset.update(status='OBSERVED', sha256=actual, bytes=len(data),
                         hash_matches=None if not expected else actual == expected)
        return asset

    def inspect(self, identity, image_id=None, revision=None, run_id=None):
        folder = self.folder(identity)
        state = self.state(identity)
        role = 'product' if state.get('mode') == 'quick_redesign' else 'reference'
        images = [item for item in state.get('images', []) if IMAGE_ID.fullmatch(item.get('id', ''))]
        targets = [item for item in images if item.get('role') == role]
        if not targets:
            raise InspectorError('任务没有可选择的图片身份。')
        image_id = image_id or targets[0]['id']
        if image_id not in [item['id'] for item in targets]:
            raise InspectorError('图片不属于本任务的工作模式。')
        revisions = []
        versions = safe_path(folder, 'versions')
        if versions.is_dir():
            revisions = [int(path.stem) for path in versions.iterdir()
                         if re.fullmatch(r'[0-9]{6}\.json', path.name) and safe_path(versions, path.name).is_file()]
        generations = safe_path(folder, 'generations')
        if generations.is_dir():
            revisions += [int(name) for name in self._directories(folder, 'generations', re.compile(r'[0-9]{6}'))
                          if safe_path(folder, f'generations/{name}/{image_id}').is_dir()]
        revisions = sorted(set(revisions + [state['revision']]), reverse=True)
        if revision is None:
            revision = next((value for value in revisions if safe_path(folder, f'generations/{value:06}/{image_id}').is_dir()), state['revision'])
        if not isinstance(revision, int) or revision < 1 or revision not in revisions:
            raise InspectorError('修订版本不在本任务的可查看范围内。')
        bucket = f'generations/{revision:06}/{image_id}'
        runs = self._directories(folder, bucket + '/runs', RUN_ID)
        pointer_doc = self.document(folder, bucket + '/current.json', 'pointer')
        pointer = pointer_doc['data'] if isinstance(pointer_doc['data'], dict) else {}
        run_id = run_id or (pointer.get('latest_run') if pointer.get('latest_run') in runs else next(iter(reversed(runs)), None))
        if run_id is not None and (not RUN_ID.fullmatch(run_id) or run_id not in runs):
            raise InspectorError('Run 不属于当前 Task、Image 和 revision。')
        selection = {'task_id': identity, 'image_id': image_id, 'revision': revision, 'run_id': run_id}
        snapshot = self.document(folder, f'versions/{revision:06}.json', 'snapshot')
        saved = snapshot['data'] if isinstance(snapshot['data'], dict) else {}
        if saved and (saved.get('id') != identity or saved.get('revision') != revision):
            raise InspectorError('确认快照身份与所选版本不一致。')
        assets = []
        for index, item in enumerate(saved.get('images', images)):
            if item.get('role') == 'product' or item.get('id') == image_id or state.get('mode') == 'quick_redesign':
                relative = item.get('file', '')
                if not IMAGE_FILE.fullmatch(relative) or not IMAGE_ID.fullmatch(item.get('id', '')):
                    raise InspectorError('图片来源路径不在白名单。')
                asset = self._asset(folder, relative, f'original-{index}', item['id'], item.get('role'), item.get('sha256'))
                asset['source'] = '所选历史快照中的图片清单' if saved else '当前 state.json 清单；历史快照缺失，历史归属未核实'
                assets.append(asset)
        inputs = [self.document(folder, 'inputs/texts.json', 'texts')]
        nodes = [{'id': 'inputs', 'label': '原始资料', 'status': inputs[0]['status'],
                  'note': '原始资料是来源陈述；SHA-256 一致不代表 SKU 身份或宣称已核实。', 'documents': inputs}]
        quick = state.get('mode') == 'quick_redesign'
        calls = [event for event in saved.get('events', []) if TASK_ID.fullmatch(event.get('call_id', ''))
                 and (event.get('action') in ('understand', 'replan') or event.get('action') == 'plan' and event.get('target') == image_id)]
        call = calls[-1] if calls and not quick else None
        planning = [self.document(folder, f"calls/{call['call_id']}/{name}", name) for name in
                    ('run.json', 'request.json', 'image_order.json', 'prompt.txt', 'response.json', 'result.json', 'applied.json', 'error.json')] if call else []
        if planning:
            call_record = planning[0]['data']
            if isinstance(call_record, dict) and call_record.get('session_id') != identity:
                raise InspectorError('Planning Call 身份不属于本任务。')
        nodes.append({'id': 'planning', 'label': 'Planning', 'status': 'NOT_APPLICABLE' if quick else 'OBSERVED' if any(doc['status'] == 'OBSERVED' for doc in planning) else 'MISSING',
                      'note': 'Quick Redesign 不执行独立 Planning。' if quick else '根据所选快照事件定位最近相关计划调用；不是全部理解修订的完整血缘。',
                      'applicable': not quick, 'call_id': call.get('call_id') if call else None, 'documents': planning})
        nodes.append({'id': 'confirmation', 'label': '输入快照' if quick else '确认版本', 'status': snapshot['status'], 'applicable': not quick,
                      'note': 'Quick 的 revision 是输入快照，不代表计划确认。' if quick else '查看原始版本快照及其确认记录；不使用今天的状态替代历史。',
                      'documents': [snapshot]})
        generation, record = [], {}
        if run_id:
            run_root = safe_path(folder, bucket + '/runs/' + run_id)
            generation = [self.document(run_root, name, name) for name in
                          ('run.json', 'plan.json', 'prompt.txt', 'request.json', 'response.json', 'error.json')]
            record = generation[0]['data'] if isinstance(generation[0]['data'], dict) else {}
            if record and (record.get('run_id') != run_id or record.get('session_id') != identity or
                           record.get('reference_id') != image_id or record.get('confirmed_revision') != revision):
                raise InspectorError('Run 内容与所选身份不一致。')
            request = generation[3]['data'] if isinstance(generation[3]['data'], dict) else {}
            for index, item in enumerate(request.get('image_order', record.get('inputs', []))):
                relative = item.get('file', '')
                if not IMAGE_FILE.fullmatch(relative):
                    raise InspectorError('实际输入图片路径不在白名单。')
                assets.append(self._asset(run_root, relative, f'run-input-{index}', f"输入 {item.get('slot', index + 1)} · {item.get('id', '?')}",
                                          item.get('role'), item.get('sha256')))
            assets.append(self._asset(run_root, 'image.png', 'output', '本次生成结果', 'output', (record.get('output') or {}).get('sha256')))
        nodes.append({'id': 'generation', 'label': 'Generation', 'status': 'OBSERVED' if any(doc['status'] == 'OBSERVED' for doc in generation) else 'MISSING',
                      'execution_status': record.get('status', 'UNKNOWN'),
                      'note': '显示实际保存的请求、Context 和响应；技术 SUCCEEDED 不代表商品外观通过。', 'documents': generation})
        reviews = []
        review_dir = safe_path(folder, bucket + '/reviews')
        if review_dir.is_dir():
            for child in sorted(review_dir.iterdir()):
                if re.fullmatch(r'[0-9a-f]{32}\.json', child.name):
                    doc = self.document(folder, bucket + '/reviews/' + child.name, child.name)
                    event = doc['data']
                    if isinstance(event, dict) and event.get('run_id') == run_id:
                        if event.get('task_id') != identity or event.get('reference_id') != image_id or event.get('confirmed_revision') != revision:
                            raise InspectorError('审核事件身份与本图不一致。')
                        reviews.append(doc)
        nodes.append({'id': 'review', 'label': 'Review / Pass', 'status': 'OBSERVED' if reviews else 'MISSING',
                      'note': '只展示明确引用本 Run 的审核事件；当前指针单独展示，不将选中版本当成 Pass。', 'documents': reviews + [pointer_doc]})
        edges = [
            {'source': 'inputs', 'target': 'planning', 'status': 'INFERRED' if call else 'MISSING', 'basis': 'Task 快照事件与 Call 目录关联；未声明完整历史血缘。'},
            {'source': 'planning', 'target': 'confirmation', 'status': 'INFERRED' if call else 'MISSING', 'basis': '根据事件 action/target/call_id 关联最近计划结果。'},
            {'source': 'confirmation', 'target': 'generation', 'status': 'OBSERVED' if run_id and generation[0]['status'] == 'OBSERVED' and saved else 'MISSING', 'basis': 'Run.confirmed_revision 与同任务快照身份关联；不证明语义或内容一致。'},
            {'source': 'generation', 'target': 'review', 'status': 'OBSERVED' if reviews else 'MISSING', 'basis': '审核事件明确记录的 Run ID。'}]
        if quick:
            edges = [{'source': 'inputs', 'target': 'generation', 'status': 'OBSERVED' if run_id else 'MISSING', 'basis': 'Quick 使用输入快照；没有独立 Planning。'}, edges[-1]]
        context = context_view(selection, state.get('mode'), nodes, assets)
        return preview({'task': {'id': identity, 'title': state.get('title', identity), 'mode': state.get('mode', 'product_pack')},
                        'selection': selection, 'images': [{'id': item['id']} for item in targets], 'revisions': revisions,
                        'runs': list(reversed(runs)), 'nodes': nodes, 'edges': edges, 'assets': assets,
                        'context_view': context,
                        'graph_view': context_graph(selection, state.get('mode'), nodes, assets, context),
                        'limitations': ['这是保存证据的关联图，不是模型内部执行图。', '文件哈希对应原文件；展示内容已脱敏并省略图片编码。',
                                        '缺少文件不等于当时没有执行；不恢复或改写原始记录。', '只展示最近相关 Planning Call；完整源码、HTTP 抓包、远端计费与模型内部根因仍未知。']})

    def asset(self, identity, image_id, revision, run_id, key):
        view = self.inspect(identity, image_id, revision, run_id)
        image_id, revision, run_id = (view['selection'][name] for name in ('image_id', 'revision', 'run_id'))
        asset = next((item for item in view['assets'] if item['key'] == key), None)
        if not asset or asset['status'] != 'OBSERVED':
            raise InspectorError('本次证据没有此图片。')
        folder = self.folder(identity)
        root = folder if key.startswith('original-') else safe_path(folder, f'generations/{revision:06}/{image_id}/runs/{run_id}')
        path = safe_path(root, asset['file'])
        if path.stat().st_size > MAX_IMAGE_BYTES:
            raise InspectorError('图片超过查看上限。')
        data = path.read_bytes()
        if sha256(data) != asset['sha256'] or contains_private(data.decode('utf-8', errors='ignore')):
            raise InspectorError('图片发生变化或包含疑似认证信息，未显示。')
        try:
            with Image.open(io.BytesIO(data)) as image:
                mime = {'PNG': 'image/png', 'JPEG': 'image/jpeg', 'WEBP': 'image/webp'}[image.format]
                image.verify()
        except (OSError, ValueError, KeyError) as error:
            raise InspectorError('证据图片无法安全预览。') from error
        return data, mime
