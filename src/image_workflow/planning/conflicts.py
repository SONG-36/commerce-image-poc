"""Listing fact disputes and version-scoped operator dispositions, without IO.

Reports are model observations, not independent fact verification. Only explicit
VISIBLE_CONTRADICTION reports block; an unseen feature is insufficient evidence.
"""

import copy
import json
import re

from file_ops import sha256
from image_workflow import Problem
from .validation import fields, PLAN_FIELDS


REPORT_INSTRUCTIONS = """额外返回 fact_issues 数组，无问题返回 []。每项包含 conflict_id（字母数字下划线短ID）、
affected_claim、text_evidence、visual_evidence、issue_type、affected_image_ids。
text_evidence.source 为 listing/description/requirements 时，quote 必须逐字摘自 original_inputs 对应字段，
不得把逐图要求、当前计划或模型总结冒充这些原文，不附 reference_id。
若依据是本次提供的逐图 Brief，source 用 slot_requirements，并提供 reference_id 与 quote；reference_id 必须在
fact_source_contract.slot_requirements_reference_ids 及本报告 affected_image_ids 中，quote 逐字摘自对应
output_slot_inputs[reference_id].requirements。不能引用其他任务、未启用图位或本次未提供的 Brief。
区分商品资料声明、商品图可见外观、参考视觉表达、运行时制作约束与模型推断。任务及逐图要求是制作范围/运营声明，
不是独立事实认证；未选择或禁止使用的资料宣称不能写回制作方案。不能由外观或示意图猜测未确认机构、功能或效果。
模型推断没有可冒充的原始 source，应放入 uncertainties/risks，不用伪造引用支撑；参考图不证明目标商品事实。
visual_evidence（product_image_ids 为本次可见商品图片ID数组，observation 为具体可见依据）、
issue_type 为 VISIBLE_CONTRADICTION 或 INSUFFICIENT_EVIDENCE；affected_image_ids 仅为
planning_id_contract.valid_reference_ids 内的受影响参考/计划ID，不是图位 ID，不得混合编号。
只有文字宣称与商品图清楚可见内容明显相反才用 VISIBLE_CONTRADICTION；未拍到、角度不足或不能验证功能用
INSUFFICIENT_EVIDENCE，不把看不见当矛盾，不要求逐条证明无矛盾宣称。报告供运营处理，不能自行裁决或改写事实。
已保存的人工处理仅适用于其版本，新增矛盾仍须报告。"""


def validate_reports(raw, state, targets, *, slot_reference_ids=None):
    values = raw.get('fact_issues')
    if not isinstance(values, list):
        raise Problem('AI 缺少结构化事实争议结果，当前计划未替换。', 502)
    products = {image['id'] for image in state['images'] if image['role'] == 'product'}
    targets = set(targets)
    slot_texts = {slot['reference_id']: slot.get('requirements', '') for slot in state.get('listing_slots', [])
                  if slot['enabled'] and slot['reference_id'] in targets}
    if slot_reference_ids is not None:
        slot_texts = {key: text for key, text in slot_texts.items() if key in slot_reference_ids}
    def require(condition):
        if not condition:
            raise ValueError('Invalid fact report')
    seen, result = set(), []
    for value in values:
        try:
            identity, text, visual = value['conflict_id'], value['text_evidence'], value['visual_evidence']
            require(isinstance(identity, str) and re.fullmatch(r'[A-Za-z0-9_]{1,80}', identity) and identity not in seen)
            require(value['issue_type'] in ('VISIBLE_CONTRADICTION', 'INSUFFICIENT_EVIDENCE'))
            require(isinstance(value['affected_claim'], str) and 0 < len(value['affected_claim']) <= 12000)
            if text['source'] in ('listing', 'description', 'requirements'):
                require('reference_id' not in text)
                source_text = state['inputs'][text['source']]
            else:
                require(text['source'] == 'slot_requirements')
                reference = text['reference_id']
                require(isinstance(reference, str) and reference in slot_texts
                        and reference in value['affected_image_ids'])
                source_text = slot_texts[reference]
            require(isinstance(text['quote'], str) and text['quote'].strip() and text['quote'] in source_text)
            require(isinstance(visual['observation'], str) and 0 < len(visual['observation']) <= 12000)
            for ids, owned in ((visual['product_image_ids'], products), (value['affected_image_ids'], targets)):
                require(isinstance(ids, list) and ids and all(isinstance(i, str) for i in ids))
                require(len(set(ids)) == len(ids) and set(ids) <= owned)
        except (ValueError, KeyError, TypeError):
            raise Problem('AI 事实争议的来源或图片关联无效，当前计划未替换。', 502) from None
        seen.add(identity)
        result.append({key: copy.deepcopy(value[key]) for key in ('conflict_id', 'affected_claim',
                       'text_evidence', 'visual_evidence', 'issue_type', 'affected_image_ids')})
    return result


def scope(state, issue):
    """Do not bind global revision: confirming another card changes no facts."""
    data = {'inputs': state['inputs'], 'images': state['images'], 'product': state.get('product'),
            'product_version': state['product_version'],
            'targets': {key: {'reference': state['references'].get(key),
                            'reference_version': state['reference_versions'].get(key),
                            'plan': state['plans'].get(key), 'version': state.get('plan_versions', {}).get(key)}
                        for key in issue['affected_image_ids']}}
    if issue['text_evidence']['source'] == 'slot_requirements':
        reference = issue['text_evidence']['reference_id']
        data['slot_requirements'] = next((slot['requirements'] for slot in state.get('listing_slots', [])
                                         if slot['enabled'] and slot['reference_id'] == reference), None)
    return sha256(json.dumps(data, ensure_ascii=False, sort_keys=True).encode())


def issue_views(state):
    result = []
    for issue in state.get('fact_issues', []):
        item = copy.deepcopy(issue)
        resolution = item.get('operator_resolution')
        item['resolution_status'] = ('RESOLVED' if resolution and resolution['scope_sha256'] == scope(state, item)
                                     else 'STALE' if resolution else 'UNRESOLVED')
        result.append(item)
    return result


def blockers(state, target):
    return [issue for issue in issue_views(state) if issue['issue_type'] == 'VISIBLE_CONTRADICTION'
            and target in issue['affected_image_ids'] and issue['resolution_status'] != 'RESOLVED']


def apply_reports(state, reports, call_id):
    # New calls cannot erase an earlier unresolved report by returning an empty list.
    for report in reports:
        state.setdefault('fact_issues', []).append({**copy.deepcopy(report),
            'conflict_id': call_id + '_' + report['conflict_id'], 'call_id': call_id,
            'reported_revision': state['revision'] + 1, 'reported_scope_sha256': scope(state, report)})


def resolve(state, body, *, clock):
    issue = next((i for i in state.get('fact_issues', []) if i['conflict_id'] == body.get('conflict_id')), None)
    decision, note = body.get('decision'), body.get('note')
    if issue is None or decision not in ('RETAIN', 'CORRECT', 'EXCLUDE'):
        raise Problem('请选择当前任务的争议及明确处理决定。')
    if not isinstance(note, str) or not note.strip() or len(note) > 12000:
        raise Problem('请填写人工依据或处理说明（最多 12000 字），不是独立真实性认证。')
    before = copy.deepcopy(issue.get('operator_resolution'))
    if decision != 'RETAIN':
        plans = body.get('plans')
        if not isinstance(plans, dict) or set(plans) != set(issue['affected_image_ids']):
            raise Problem('修正或移除宣称须提交所有受影响图位的修订计划。')
        try:
            cleaned = {key: fields(plan, PLAN_FIELDS) for key, plan in plans.items()}
            if any(len(value) > 12000 for plan in cleaned.values() for value in plan.values()):
                raise Problem('计划字段超过 12000 字。')
        except Problem as error:
            raise Problem('请完整填写修订计划，每项最多 12000 字。') from error
        for key, plan in cleaned.items():
            state['plans'][key] = plan
            state.setdefault('plan_versions', {})[key] = state.get('plan_versions', {}).get(key, 0) + 1
            state['plan_context'][key] = [state['product_version'], state['reference_versions'].get(key, 0)]
    for key in issue['affected_image_ids']:
        state.setdefault('plan_confirmations', {}).pop(key, None)
    state['confirmed'] = False
    resolution = {'decision': decision, 'note': note, 'revision': state['revision'] + 1,
                  'at': clock(), 'scope_sha256': scope(state, issue), 'source': 'OPERATOR_DECISION_NOT_VERIFICATION'}
    issue['operator_resolution'] = resolution
    return {'action': 'resolve_conflict', 'target': None, 'conflict_id': issue['conflict_id'],
            'before': before, 'after': copy.deepcopy(resolution), 'feedback': note}


def generation_dispositions(state, target):
    return [issue for issue in issue_views(state) if target in issue['affected_image_ids']]
