"""Pure graph projection of InspectorReader's already parsed Evidence.

No file access, Prompt reconstruction, model calls or business state changes.
An arrow describes the strength of a saved association, never model attention.
"""

import hashlib
import json
import re


def prompt_segments(prompt, tag, *, quick_v1=False):
    """Locate saved literal sections, without rebuilding a historical Prompt."""
    if not isinstance(prompt, str):
        return []
    if quick_v1:
        # These are exact saved formats, not guesses based on today's builder.
        fact_labels = ('商品事实说明：', '运营补充商品资料（来源陈述，非独立认证）：')
        headings = ('整体要求：', *fact_labels, '本图可选补充要求：', '本次修改意见：')
        positions = {heading: list(re.finditer(r'^' + re.escape(heading) + r'\n', prompt, re.M))
                     for heading in headings}
        facts = [heading for heading in fact_labels if positions[heading]]
        if len(facts) != 1:
            return []
        fact = facts[0]
        sequence = ('整体要求：', fact, '本图可选补充要求：', '本次修改意见：')
        if any(len(positions[heading]) != 1 for heading in sequence):
            return []
        offsets = [positions[heading][0].start() for heading in sequence]
        if offsets != sorted(offsets):
            return []
        labels = {'operator_design_requirements': ('整体要求：', fact),
                  'product_constraints_from_operator': (fact, '本图可选补充要求：'),
                  'revision_feedback': ('本次修改意见：', None),
                  'slot_requirements': ('本图可选补充要求：', '本次修改意见：')}
        start, end = labels[tag]
        expression = r'^' + re.escape(start) + r'\n(.*?)\n' + (r'(?=^' + re.escape(end) + r'\n)' if end else r'\Z')
    else:
        expression = r'<' + tag + r'>\n?(.*?)\n?</' + tag + '>'
    return list(re.finditer(expression, prompt, re.S | re.M))


def context_graph(selection, mode, documents, assets, context):
    if mode != 'quick_redesign':
        return {'supported': False, 'nodes': [], 'edges': [],
                'note': 'V0.7 Context 图仅解释 Quick Run；商品图包仍可查看已有执行证据。'}
    if selection['run_id'] is None:
        return {'supported': False, 'awaiting_run': True, 'nodes': [], 'edges': [],
                'note': '当前图片尚无保存的 Run；没有重建或虚构请求。生成结束后可只读刷新。'}
    graph_id = 'quick:' + ':'.join(str(selection[key]) for key in ('task_id', 'image_id', 'revision', 'run_id'))
    docs = {(node['id'], doc['key']): doc for node in documents for doc in node['documents']}
    cards = {card['id']: card for card in context['cards']}
    run = docs.get(('generation', 'run.json'), {}).get('data') or {}
    request = docs.get(('generation', 'request.json'), {}).get('data') or {}
    snapshot = docs.get(('generation', 'plan.json'), {}).get('data') or {}
    run = run if isinstance(run, dict) else {}
    request = request if isinstance(request, dict) else {}
    snapshot = snapshot if isinstance(snapshot, dict) else {}
    prefix = f"generations/{selection['revision']:06}/{selection['image_id']}"
    run_prefix = prefix + '/runs/' + str(selection['run_id']) + '/'

    def ref(key, pointer='', node='generation'):
        item = docs.get((node, key), {})
        value = item.get('data')
        pointer_exists = item.get('status') == 'OBSERVED'
        if pointer:
            for token in pointer.lstrip('/').split('/'):
                token = token.replace('~1', '/').replace('~0', '~')
                if isinstance(value, dict) and token in value:
                    value = value[token]
                elif isinstance(value, list) and token.isdigit() and int(token) < len(value):
                    value = value[int(token)]
                else:
                    pointer_exists = False
                    break
        return {'scope': 'run' if node == 'generation' else 'task', 'node_id': node,
                'document_key': key, 'file': item.get('file', key), 'pointer': pointer,
                'relative_path': run_prefix + item.get('file', key) if node == 'generation' else item.get('file', key),
                'sha256': item.get('sha256'), 'exists': item.get('status') == 'OBSERVED',
                'pointer_exists': pointer_exists,
                'status': item.get('status', 'MISSING')}

    def observed(key):
        return docs.get(('generation', key), {}).get('status') == 'OBSERVED'

    def identifier(key):
        return graph_id + ':' + key

    requirements, facts, feedback = cards['requirements']['fields'][:3]
    order = cards['request']['images']
    product = cards['product']['images']
    reference = [image for image in order if image.get('role') not in ('original', 'product', 'current_image')]
    parent = [image for image in order if image.get('role') == 'current_image']
    first = observed('run.json') and 'parent_run_id' in run and run['parent_run_id'] is None and run.get('feedback') == ''
    reviews = [doc for doc in docs.values() if doc.get('key') != 'pointer' and
               isinstance(doc.get('data'), dict) and doc['data'].get('run_id') == selection['run_id'] and
               doc in next(node['documents'] for node in documents if node['id'] == 'review')]
    review_refs = [ref(doc['key'], node='review') for doc in reviews] or [
        {'scope': 'task', 'node_id': 'review', 'document_key': None, 'file': prefix + '/reviews/',
         'relative_path': prefix + '/reviews/', 'pointer': '', 'sha256': None, 'exists': False,
         'status': 'MISSING', 'event_id': None}]
    nodes = []

    def add(key, label, kind='ARTIFACT', *, fields=(), images=(), refs=(), status=None, note='', main=True):
        if status is None:
            status = 'OBSERVED' if any(item.get('status') == 'OBSERVED' for item in fields) or any(
                item.get('status') == 'OBSERVED' for item in images) else 'UNKNOWN'
        refs = list(refs)
        for image in images:
            asset = next((a for a in assets if a['key'] == image.get('asset_key')), {})
            refs.append({'scope': 'task' if str(asset.get('key', '')).startswith('original-') else 'run',
                         'node_id': 'generation', 'document_key': None, 'file': asset.get('file'),
                         'relative_path': ('' if str(asset.get('key', '')).startswith('original-') else run_prefix) + str(asset.get('file', '')),
                         'pointer': '', 'asset_key': image.get('asset_key'), 'sha256': asset.get('sha256'),
                         'exists': asset.get('status') == 'OBSERVED', 'status': asset.get('status', 'MISSING')})
        nodes.append({'id': identifier(key), 'key': key, 'kind': kind, 'subtype': key,
                      'label': label, 'summary': note, 'evidence_status': status,
                      'execution_status': run.get('status', 'UNKNOWN') if key == 'P02' else 'UNKNOWN',
                      'event_id': run.get('operation_id') if key == 'P02' else None,
                      'fields': list(fields), 'images': list(images), 'asset_keys': [i.get('asset_key') for i in images],
                      'evidence_refs': list(refs), 'consistency_checks': [], 'code_refs': [],
                      'uncertainty_reason': note, 'default_visible': main,
                      'detail_levels': [1, 2, 3]})

    add('N01', '商品原图', images=product, refs=[ref('snapshot', '/images', 'confirmation')],
        note='本图商品依据；哈希一致不证明 SKU 身份正确。')
    add('N02', '参考与辅助图片', images=reference, fields=cards['references']['fields'],
        status='N/A' if isinstance(request.get('image_order'), list) and not reference else
               'MISSING' if reference and all(image['status'] == 'MISSING' for image in reference) else
               'OBSERVED' if reference else 'UNKNOWN',
        refs=[ref('request.json', '/image_order')], note='角色及顺序来自保存清单；不证明模型采用了参考图的视觉特征。')
    add('N03', '运营设计要求', fields=[requirements, *cards['requirements']['fields'][3:]], refs=[ref('plan.json', '/original_inputs/requirements')],
        note='本次 Context 留存的整体要求，不用当前任务要求补写。')
    add('N04', '商品事实约束', fields=[facts], refs=[ref('plan.json', '/original_inputs/product_facts')],
        note='运营提供的来源陈述，不等于已核实事实。')
    add('N05', 'Listing / 描述', fields=cards['product']['fields'][1:],
        refs=[ref('snapshot', '/inputs', 'confirmation')], main=False,
        note='资料快照；未逐字出现在 Prompt 不直接等于业务信息丢失。')
    add('N06', 'Run Context 快照', fields=cards['assembly']['fields'], refs=[ref('plan.json')],
        status='MISSING' if not observed('plan.json') else None,
        note='Quick 的 plan.json 是本次 Context 快照，不是独立 Planning，也不等于整份 SDK 输入。')
    add('N07', '有序图片清单', images=order, refs=[ref('request.json', '/image_order'), ref('run.json', '/inputs')],
        note='保留数组顺序与 slot；request 缺失时仅 Run.inputs 可见，实际请求清单未知。')
    add('N08', '最终 Prompt', fields=[context['prompt'], context['prompt_file']],
        refs=[ref('request.json', '/prompt'), ref('prompt.txt')],
        note='Prompt 留存；request.prompt 缺失时仅有 prompt.txt，实际请求文字仍 UNKNOWN。不用当前代码重建。')
    add('N09', 'Images Request', fields=cards['request']['fields'], images=order,
        refs=[ref('request.json')], status='OBSERVED' if observed('request.json') else 'MISSING',
        note='应用保存的请求元数据和文件引用；没有完整 SDK kwargs / multipart 或远端收包证明。')
    response = docs.get(('generation', 'response.json'), {}).get('data')
    usage = response.get('usage') if isinstance(response, dict) else None
    add('N10', '模型响应留存', refs=[ref('response.json'), ref('error.json')],
        fields=[{'label': '响应中保存的 Usage', 'value': ' · '.join(f'{key}={value}' for key, value in usage.items()) if isinstance(usage, dict) else None,
                 'status': 'OBSERVED' if isinstance(usage, dict) else 'UNKNOWN', 'sources': [ref('response.json', '/usage')]},
                *cards['output']['fields'][3:]],
        status='OBSERVED' if observed('response.json') else 'MISSING',
        note='响应文件留存；与调用活动的关联依赖同一 Run，远端来源不能单独认证。')
    add('N11', '生成图片', fields=cards['output']['fields'], images=cards['output']['images'],
        refs=[ref('run.json', '/output')], status=next((a['status'] for a in assets if a['key'] == 'output'), 'MISSING'),
        note='本地输出归属；SUCCEEDED、可解码和 MATCH 均不等于商品质量或人工 Pass。')
    add('N12', '审核事件', refs=review_refs, main=False, status='OBSERVED' if reviews else 'MISSING',
        fields=[{'label': '明确关联本 Run 的审核动作', 'value': '、'.join(str(doc['data'].get('action', 'UNKNOWN')) for doc in reviews),
                 'status': 'OBSERVED' if reviews else 'UNKNOWN', 'sources': review_refs}],
        note='只展示明确关联本 Run 的事件；没有事件不能推断人工已通过或未审核。')
    add('N13', '本次修改意见', fields=[feedback], refs=[ref('run.json', '/feedback')],
        status='N/A' if first else feedback['status'], main=False, note='首次生成不适用；仅本次反馈，不混入全部修改历史。')
    add('N14', '父图片版本', images=parent, refs=[ref('run.json', '/parent_run_id'), ref('request.json', '/image_order')],
        status='N/A' if first else 'OBSERVED' if parent else 'UNKNOWN', main=False,
        note='当前编辑输入与父 Run 关系；缺少记录时不借用其他版本。')
    add('P01', 'Context Assembly', 'ACTIVITY', refs=[ref('plan.json'), ref('prompt.txt')],
        status='INFERRED' if observed('plan.json') or observed('prompt.txt') else 'UNKNOWN',
        note='逻辑组装活动：有产物，未保存独立活动 trace / 时间 / 历史函数身份。')
    nodes[-1]['consistency_checks'] = cards['assembly']['checks']
    add('P02', 'Images API 本地尝试', 'ACTIVITY',
        fields=[*[f for f in cards['request']['fields'] if f['label'] in ('SDK 调用尝试标记', 'OpenAI request_id')], *cards['output']['fields']],
        refs=[ref('run.json', '/api_call_attempted'), ref('run.json', '/operation_id')],
        status='OBSERVED' if observed('run.json') and 'api_call_attempted' in run else 'UNKNOWN',
        note='本地 SDK 尝试标记不等于远端执行确认；历史 transport / 费用不能由该标记推断。')
    add('P03', '人工审核', 'ACTIVITY', refs=review_refs, main=False,
        status='OBSERVED' if reviews else 'MISSING', note='以明确的审核事件为依据，不将 selected_run 视为 passed_run。')
    edges = []

    def edge(key, source, target, relation, status, refs, claim, checks=(), reason=''):
        # Missing prerequisites may lower an association, never strengthen it.
        if status in ('OBSERVED', 'INFERRED') and any(not item['exists'] or item.get('pointer_exists') is False for item in refs):
            status = 'UNKNOWN'
        edges.append({'id': identifier(key), 'key': key, 'source': identifier(source), 'target': identifier(target),
                      'relation_type': relation, 'claim': claim, 'evidence_status': status,
                      'evidence_refs': refs, 'consistency_checks': list(checks),
                      'uncertainty_reason': reason or '只描述保存证据的关联，不代表模型语义或视觉质量通过。'})

    checks = cards['assembly']['checks']
    def check(label, result, refs):
        return {'label': label, 'result': result, 'sources': refs, 'note': '仅字节 / 字段一致性，不是语义验收。'}
    for key, source, role in [('E01', 'N01', ('original', 'product')), ('E02', 'N02', ('design_reference', 'reference', 'auxiliary_reference'))]:
        matches = [item for item in order if item['role'] in role]
        refs = [ref('request.json', '/image_order/' + str(item['position'] - 1)) for item in matches] or [ref('request.json', '/image_order')]
        result = 'MATCH' if matches and all(i['hash_matches'] is True for i in matches) else 'MISMATCH' if any(i['hash_matches'] is False for i in matches) else 'UNKNOWN'
        edge(key, source, 'N07', 'USED_AS', 'OBSERVED' if matches else 'UNKNOWN', refs,
             '图片按保存的角色与数组位置进入有序清单。', [check('文件与清单哈希', result, refs)])
    for key, source, pointer in [('E03', 'N03', '/original_inputs/requirements'), ('E04', 'N04', '/original_inputs/product_facts'), ('E05', 'N05', '/original_inputs')]:
        valid = all(f['status'] == 'OBSERVED' for f in cards['assembly']['fields'])
        comparisons = []
        if key == 'E05':
            saved_inputs = docs.get(('confirmation', 'snapshot'), {}).get('data') or {}
            saved_inputs = saved_inputs.get('inputs', {}) if isinstance(saved_inputs, dict) else {}
            original_inputs = snapshot.get('original_inputs', {})
            original_inputs = original_inputs if isinstance(original_inputs, dict) else {}
            for name in ('listing', 'description'):
                result = ('MATCH' if saved_inputs[name] == original_inputs[name] else 'MISMATCH') if name in saved_inputs and name in original_inputs else 'UNKNOWN'
                comparisons.append({'label': name + ' 快照 → Context', 'result': result,
                                    'sources': [ref('snapshot', '/inputs/' + name, 'confirmation'), ref('plan.json', '/original_inputs/' + name)],
                                    'note': '只核对留存 Context，不将未逐字进入 Prompt 判为丢失。'})
            valid = valid and all(c['result'] == 'MATCH' for c in comparisons)
        edge(key, source, 'N06', 'INCLUDED_IN', 'OBSERVED' if valid else 'UNKNOWN', [ref('plan.json', pointer)],
             '字段保存在本 Run 的 Context 中；不是整个 Context 被提交的证明。', comparisons)
    for key, source, refs in [('E06', 'N03', [ref('plan.json', '/original_inputs/requirements')]),
                               ('E07', 'N04', [ref('plan.json', '/original_inputs/product_facts')]),
                               ('E08', 'N07', [ref('request.json', '/image_order')])]:
        edge(key, source, 'P01', 'USED_AS', 'INFERRED', refs, '保存产物与逻辑组装有关；没有独立活动输入 trace。')
    digest = hashlib.sha256(json.dumps(snapshot, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    edge('E09', 'P01', 'N06', 'PRODUCED', 'INFERRED', [ref('plan.json'), ref('request.json', '/context_sha256')],
         '存在 Context 产物与其 canonical hash 引用。',
         [check('Context canonical hash', 'MATCH' if observed('plan.json') and request.get('context_sha256') == digest else 'UNKNOWN' if not request.get('context_sha256') else 'MISMATCH', [ref('request.json', '/context_sha256'), ref('plan.json')])])
    edge('E10', 'P01', 'N08', 'ASSEMBLED_INTO', 'INFERRED', [ref('prompt.txt'), ref('request.json', '/prompt')],
         '留存的 Prompt 是逻辑组装产物，未认证确切历史构建函数。', checks[3:5])
    prompt = request.get('prompt')
    for key, source, field, tag, index in [('E11', 'N03', requirements, 'operator_design_requirements', 0),
                                           ('E12', 'N04', facts, 'product_constraints_from_operator', 1)]:
        refs = [ref('plan.json', '/original_inputs/' + ('requirements' if index == 0 else 'product_facts')), ref('request.json', '/prompt')]
        matches = prompt_segments(prompt, tag, quick_v1=snapshot.get('quick_business_version') == 'v1')
        match = matches[0] if len(matches) == 1 else None
        if match:
            refs[-1].update(text_span={'start': match.start(1), 'end': match.end(1), 'unit': 'unicode_code_points'},
                            line_range=[prompt[:match.start(1)].count('\n') + 1, prompt[:match.end(1)].count('\n') + 1])
        edge(key, source, 'N08', 'INCLUDED_IN', 'OBSERVED' if checks[index]['result'] == 'MATCH' else 'UNKNOWN', refs,
             '唯一保存标签中的原文一致；不证明模型遵守。', [checks[index]])
    edge('E13', 'N08', 'N09', 'INCLUDED_IN', 'OBSERVED', [ref('request.json', '/prompt'), ref('prompt.txt')],
         'Prompt 文字保存在请求元数据中。', checks[3:5])
    edge('E14', 'N07', 'N09', 'INCLUDED_IN', 'OBSERVED', [ref('request.json', '/image_order'), ref('run.json', '/inputs')],
         '包含的是有序图片身份元数据；图片原始字节不内嵌在 request.json。', checks[5:7])
    edge('E15', 'N09', 'P02', 'SUBMITTED_WITH', 'INFERRED', [ref('request.json'), ref('run.json', '/api_call_attempted')],
         '保存请求与本地 SDK 尝试关联，未保存完整 SDK 实参或远端收包。',
         [check('请求 / Run 模型', 'UNKNOWN' if not request.get('model') or not run.get('model') else 'MATCH' if request['model'] == run['model'] else 'MISMATCH', [ref('request.json', '/model'), ref('run.json', '/model')]),
          check('请求 / Run 参数', 'UNKNOWN' if not request or not isinstance(run.get('parameters'), dict) else 'MATCH' if all(request.get(k) == run['parameters'].get(k) for k in ('n', 'quality', 'size', 'output_format')) else 'MISMATCH', [ref('request.json'), ref('run.json', '/parameters')]),
          checks[5]])
    edge('E16', 'P02', 'N10', 'PRODUCED', 'INFERRED', [ref('run.json', '/usage'), ref('response.json')],
         '响应与调用同属 Run 目录；响应本身未必包含 request_id。',
         [check('响应 / Run Usage', 'UNKNOWN' if usage is None or run.get('usage') is None else 'MATCH' if usage == run['usage'] else 'MISMATCH', [ref('response.json', '/usage'), ref('run.json', '/usage')])])
    output = next((a for a in assets if a['key'] == 'output'), {})
    edge('E17', 'P02', 'N11', 'PRODUCED', 'OBSERVED' if (run.get('output') or {}).get('file') == 'image.png' and output.get('status') == 'OBSERVED' else 'UNKNOWN',
         [ref('run.json', '/output')], 'Run 明确关联本地图片文件；不是远端生成或人工接受的证明。',
         [check('输出文件哈希', 'MATCH' if output.get('hash_matches') is True else 'MISMATCH' if output.get('hash_matches') is False else 'UNKNOWN', [ref('run.json', '/output/sha256')])])
    edge('E18', 'N11', 'P03', 'USED_AS', 'OBSERVED' if reviews else 'UNKNOWN', review_refs,
         '只在审核事件明确引用本 Run 时关联人工审核。')
    edge('E19', 'P03', 'N12', 'PRODUCED', 'OBSERVED' if reviews else 'UNKNOWN', review_refs,
         '审核产物需要实际事件；缺失时不编造 Pass。')
    edge('E20', 'N13', 'P01', 'USED_AS', 'N/A' if first else 'INFERRED', [ref('run.json', '/feedback')],
         '仅本次编辑反馈；首次生成不适用。', checks[2:3])
    edge('E21', 'N14', 'N07', 'USED_AS', 'N/A' if first else 'OBSERVED' if parent else 'UNKNOWN',
         [ref('run.json', '/parent_run_id'), ref('request.json', '/image_order')], '编辑时父图作为 current_image 输入；首次生成不适用。')
    stages = [('输入依据', ['N01', 'N02', 'N03', 'N04']), ('Context', ['P01', 'N06', 'N08']),
              ('模型请求', ['N07', 'N09']), ('执行', ['P02', 'N10']), ('输出', ['N11', 'N12', 'P03'])]
    return {'schema_version': 1, 'supported': True, 'graph_id': graph_id, 'selection': dict(selection),
            'execution_environment': {'value': 'UNKNOWN', 'source': 'Run 未保存可认证的 transport 身份',
                                      'note': '当前预览环境另示；不能由模型名、Usage 或 request_id 猜测历史是否真实付费。'},
            'nodes': nodes, 'edges': edges,
            'stages': [{'label': label, 'node_ids': [identifier(key) for key in keys]} for label, keys in stages],
            'comparison': context['comparison'], 'warnings': context['warnings']}
