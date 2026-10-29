"""Call-local Listing Knowledge projection, not a product-fact recognizer.

Existing Tasks have no structured method qualifications. Unless an operator
supplies explicit per-call assertions with owned sources, conditions stay
UNKNOWN. Quotes are matched exactly, never interpreted with keywords. Source
existence/role checks are not independent verification of the assertion.
"""

from dataclasses import asdict, dataclass
import hashlib
import json

from image_workflow.errors import Problem
from image_workflow.knowledge import ConditionEvidence, MethodSelectionContext, load_registry, select_methods
from .request import listing_slot_inputs, reference_ids


DEFAULT_CHAR_BUDGET = 12000
HEADER = """PROFESSIONAL DESIGN METHODS
以下是可选专业制作方法（HOW TO PRESENT），不是商品事实（WHAT IS TRUE）、平台硬规则或商品认证。
BUSINESS FACT 来自当前商品资料及已允许的来源；OPERATOR REQUIREMENT 是运营制作要求；DESIGN REFERENCE 是参考表达；以下仅为 PROFESSIONAL METHOD。
不得扩大原有事实权限或改写必保留要求。仅对 applications 指定的 reference_id 考虑方法，不强制套用，也不为展示知识使用而编造商品或设计结构。
CONDITIONAL 必须先检查素材是否支持并保留 missing_conditions；不得说成已确认可执行。仍缺依据时不用该方法，并在原 risks 字段说明。
知识来源仍待核查，候选进入请求不证明模型采用。保持原五字段 Plan、合法 reference ID、来源引用校验和运营确认流程。
"""


def validate_options(*, knowledge_enabled=False, knowledge_conditions=None, knowledge_char_budget=DEFAULT_CHAR_BUDGET):
    if type(knowledge_enabled) is not bool:
        raise Problem('knowledge_enabled 必须为明确的布尔值。')
    if type(knowledge_char_budget) is not int or not 256 <= knowledge_char_budget <= DEFAULT_CHAR_BUDGET:
        raise Problem('Knowledge 注入字符预算必须为 256～12000 的整数。')
    if knowledge_conditions is not None and not isinstance(knowledge_conditions, dict):
        raise Problem('Knowledge 条件必须按本次 reference ID 提供。')
    if not knowledge_enabled and (knowledge_conditions is not None or knowledge_char_budget != DEFAULT_CHAR_BUDGET):
        raise Problem('Knowledge 已关闭，不能附带会被忽略的实验条件或预算。')


def _hash(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _source(state, reference, slot, source):
    """Return source role, stable citation and actual data, without file access."""
    if not isinstance(source, dict):
        raise Problem('Knowledge 来源必须是当前任务的结构化引用。')
    kind = source.get('source')
    prefix = f"task:{state['id']}@{state['revision']}"
    if kind in ('listing', 'description', 'requirements', 'slot_requirements'):
        if set(source) != {'source', 'quote'}:
            raise Problem('Knowledge 文字来源仅接受来源类型和原文引用。')
        text = slot['requirements'] if kind == 'slot_requirements' else state['inputs'].get(kind, '')
        quote = source['quote']
        if not isinstance(quote, str) or not quote.strip() or len(quote) > 12000 or quote not in text:
            raise Problem('Knowledge 条件的原文引用与当前来源不一致。')
        path = f'output_slot_inputs/{reference}/requirements' if kind == 'slot_requirements' else f'original_inputs/{kind}'
        role = 'PERMITTED_CLAIM' if kind in ('listing', 'description') else 'OPERATOR_INPUT'
        return role, prefix + '/' + path + '#quote-sha256=' + _hash(quote), {
            **source, 'path': path, 'source_text_sha256': _hash(text)}
    if kind == 'product_image':
        if set(source) != {'source', 'image_id'}:
            raise Problem('Knowledge 商品素材来源仅接受当前 product ID。')
        image = next((item for item in state['images'] if item['id'] == source['image_id'] and item['role'] == 'product'), None)
        if image is None:
            raise Problem('Knowledge 商品素材必须属于当前 Task 的 product。')
        return 'PRODUCT_MATERIAL', prefix + '/images/' + image['id'], {
            **source, 'sha256': image['sha256'], 'role': image['role']}
    if kind == 'output_size':
        if set(source) != {'source', 'value'} or source['value'] != slot['output_size']:
            raise Problem('Knowledge 输出尺寸必须与本图位当前配置一致。')
        return 'OUTPUT_SPEC', prefix + f'/output_slot_inputs/{reference}/output_size', dict(source)
    raise Problem('不接受模型推断、参考商品事实、外部路径或其他任务作为 Knowledge 条件来源。')


def _conditions(state, reference, slot, declarations):
    if not isinstance(declarations, list) or len(declarations) > 13:
        raise Problem('每张参考的 Knowledge 条件必须为最多 13 项的列表。')
    result, sources = [], []
    for declaration in declarations:
        if not isinstance(declaration, dict) or set(declaration) != {'condition', 'value', 'sources'}:
            raise Problem('Knowledge 条件只接受 condition、value 和 sources。')
        rows = declaration['sources']
        if not isinstance(rows, list) or len(rows) > 4:
            raise Problem('每项 Knowledge 条件需要有限的当前任务来源。')
        resolved = [_source(state, reference, slot, source) for source in rows]
        roles = {item[0] for item in resolved}
        condition = declaration['condition']
        # Size alone is not a mobile-display requirement or proof of actual copy.
        if condition == 'readability_target' and 'OUTPUT_SPEC' in roles:
            raise Problem('显示目标需要明确运营要求，不能从输出尺寸猜测。')
        if condition == 'copy_and_size_available' and declaration['value'] is not None:
            if 'OUTPUT_SPEC' not in roles or not roles.intersection({'OPERATOR_INPUT', 'PERMITTED_CLAIM'}):
                raise Problem('文案与尺寸条件须同时引用当前文字资料和本图输出尺寸。')
            role = 'OUTPUT_SPEC'
        else:
            if len(roles) > 1:
                raise Problem('同一 Knowledge 条件的来源角色必须清楚，不混合事实与制作要求。')
            role = next(iter(roles), None)
        try:
            item = ConditionEvidence(condition, declaration['value'], role, tuple(row[1] for row in resolved))
        except ValueError as error:
            raise Problem(str(error)) from error
        result.append(item)
        sources.append({**asdict(item), 'sources': [row[2] for row in resolved],
                        'authority': 'OPERATOR_DECLARED_FOR_THIS_CALL_NOT_INDEPENDENTLY_VERIFIED'})
    return tuple(result), sources


@dataclass(frozen=True)
class KnowledgeContext:
    effective_text: str
    evidence: dict


def prepare_knowledge(state, action, target, *, knowledge_conditions=None, knowledge_char_budget=DEFAULT_CHAR_BUDGET):
    """Use B-01 once per classified reference; return one budgeted, deduped chapter."""
    validate_options(knowledge_enabled=True, knowledge_conditions=knowledge_conditions,
                     knowledge_char_budget=knowledge_char_budget)
    if state.get('mode', 'product_pack') != 'product_pack':
        raise Problem('Knowledge 本轮只用于 Listing Planning。')
    ids = reference_ids(state)
    applicable = [target] if target else ids
    if any(identity not in ids for identity in applicable):
        raise Problem('Knowledge 参考身份不属于本次 Planning。')
    declarations = knowledge_conditions or {}
    if any(identity not in applicable for identity in declarations):
        raise Problem('Knowledge 条件含有本次调用之外的参考身份。')
    supported = action in ('understand', 'replan', 'plan')
    if not supported and declarations:
        raise Problem('本次操作不制作 Plan，不能附带专业方法条件。')
    registry = load_registry()
    slots = listing_slot_inputs(state, target)
    selections, proposed = {}, {}
    for identity in applicable:
        if not supported or identity not in slots:
            if identity in declarations:
                raise Problem('未分类历史参考不能猜测图位并使用专业方法。')
            selections[identity] = {'status': 'NOT_A_DESIGN_PLANNING_ACTION' if not supported else 'UNCLASSIFIED_REFERENCE',
                                    'selected': [], 'not_selected': [],
                                    'missing_conditions': ['design_planning_action'] if not supported else ['classified_design_slot']}
            continue
        slot = slots[identity]
        conditions, sources = _conditions(state, identity, slot, declarations.get(identity, []))
        try:
            context = MethodSelectionContext('product_pack', slot['type'], output_intent=slot['requirements'], conditions=conditions)
            selection = select_methods(context, registry, max_candidates=3)
        except ValueError as error:
            raise Problem(str(error)) from error
        selections[identity] = {**asdict(selection), 'condition_sources': sources}
        for candidate in selection.selected:
            proposed.setdefault(candidate.method_id, []).append((identity, candidate))
    # A method's body occurs once; applicability/conditions remain per reference.
    order = sorted(proposed, key=lambda identity: (
        min(0 if row.eligibility == 'ELIGIBLE' else 1 for _, row in proposed[identity]),
        min(row.priority for _, row in proposed[identity]), identity))
    injected, omitted = [], []
    text = ''
    for identity in order:
        card = registry.get(identity)
        method = {'method_id': identity, 'method_version': card.version, 'content_hash': card.content_hash,
                  'applications': [{'reference_id': reference, 'eligibility': candidate.eligibility,
                                    'missing_conditions': list(candidate.missing_conditions)}
                                   for reference, candidate in proposed[identity]], 'card': card.to_dict()}
        attempt = HEADER + json.dumps({'methods': injected + [method]}, ensure_ascii=False, indent=2)
        if len(attempt) > knowledge_char_budget:
            omitted.append({'method_id': identity, 'reason': 'CONTENT_BUDGET',
                            'applicable_reference_ids': [reference for reference, _ in proposed[identity]]})
        else:
            injected.append(method)
            text = attempt
    by_id = {item['method_id']: item for item in injected}
    evidence = {'knowledge_enabled': True, 'selection_stage': 'METHOD_CANDIDATE_SELECTED',
                'status': 'METHODS_PROVIDED' if injected else 'NO_METHOD_SELECTED',
                'method_ids': list(by_id),
                'method_versions': {key: item['method_version'] for key, item in by_id.items()},
                'content_hashes': {key: item['content_hash'] for key, item in by_id.items()},
                'source_references': {key: item['card']['source_reference'] for key, item in by_id.items()},
                'selection_basis': selections,
                'eligibility': {key: item['applications'] for key, item in by_id.items()},
                'missing_conditions': {key: {row['reference_id']: row['missing_conditions'] for row in item['applications']}
                                       for key, item in by_id.items()},
                'effective_knowledge_text': text, 'effective_knowledge_text_sha256': _hash(text),
                'applicable_reference_ids': [key for key in applicable if any(
                    row['reference_id'] == key for item in injected for row in item['applications'])],
                'model_adoption_status': 'MODEL_ADOPTION_UNKNOWN', 'content_budget': knowledge_char_budget,
                'content_budget_unit': 'UNICODE_CHARACTERS',
                'budget_omissions': omitted,
                'fact_boundary': 'PROFESSIONAL_METHOD_ONLY; NO_PRODUCT_FACT_CERTIFICATION_OR_OPERATOR_PASS'}
    return KnowledgeContext(text, evidence)
