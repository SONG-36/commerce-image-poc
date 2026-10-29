"""Task confirmation, invalidation and Planning-result state transitions.

No filesystem, Flask, SDK or execution registry. Callers supply time explicitly.
"""

import copy
import json

from file_ops import sha256
from image_workflow import Problem
from image_workflow.planning.request import reference_ids
from image_workflow.planning.conflicts import apply_reports, blockers


def context_version(state, ref_id):
    return [state["product_version"], state["reference_versions"].get(ref_id, 0)]


def stale_ids(state):
    return [ref_id for ref_id in reference_ids(state) if ref_id in state["plans"] and state["plan_context"].get(ref_id) != context_version(state, ref_id)]


def plan_status(state, target):
    plan = state['plans'].get(target)
    version = state.get('plan_versions', {}).get(target, 1 if plan else 0)
    entry = state.get('plan_confirmations', {}).get(target)
    legacy = bool(not state.get('plan_confirmations') and state.get('confirmed') and plan and target not in stale_ids(state))
    digest = sha256(json.dumps(plan, ensure_ascii=False, sort_keys=True).encode())
    if legacy:
        entry = {'plan_version': version, 'revision': state['revision'], 'plan_sha256': digest,
                 'context': context_version(state, target), 'confirmed_at': state.get('updated_at', state['created_at']),
                 'source': 'LEGACY_GLOBAL_CONFIRMED'}
    current = bool(entry and plan and target not in stale_ids(state)
                   and entry['plan_version'] == version and entry['plan_sha256'] == digest
                   and entry['context'] == context_version(state, target)
                   and isinstance(entry['revision'], int) and 1 <= entry['revision'] <= state['revision'])
    disputes = blockers(state, target)
    return {'plan_version': version, 'confirmed': current and not disputes, 'confirmation': entry, 'legacy': legacy,
            **({'fact_conflict_ids': [issue['conflict_id'] for issue in disputes]} if disputes else {})}


def materialize_confirmations(state):
    """Only on an explicit write: retain legacy confirmations before changing a plan."""
    statuses = {target: plan_status(state, target) for target in reference_ids(state)}
    state['plan_versions'] = {target: item['plan_version'] for target, item in statuses.items()}
    state['plan_confirmations'] = {target: copy.deepcopy(item['confirmation']) for target, item in statuses.items() if item['confirmation']}


def confirm_plan(state, target, body, *, clock):
    """Return one confirmation event, or None for the existing no-op."""
    ids = reference_ids(state)
    if target not in ids or target not in state['plans'] or target in stale_ids(state):
        raise Problem('请在对应卡片确认已采用最新理解的本图计划。')
    status = plan_status(state, target)
    if status.get('fact_conflict_ids'):
        raise Problem('本图存在未处理或版本已过期的图文事实争议，请先查看依据并作出人工处理决定。', 409)
    if body.get('plan_version', status['plan_version']) != status['plan_version']:
        raise Problem('本图计划版本已改变，请刷新后确认。', 409)
    if status['confirmed']:
        return None
    materialize_confirmations(state)
    state['plan_confirmations'][target] = {
        'plan_version': status['plan_version'], 'revision': state['revision'] + 1,
        'plan_sha256': sha256(json.dumps(state['plans'][target], ensure_ascii=False, sort_keys=True).encode()),
        'context': context_version(state, target), 'confirmed_at': clock()}
    state['plan_confirmations'][target]['source'] = 'EXPLICIT_PER_IMAGE'
    return {"action": "confirm", "target": target, "feedback": "", "plan_version": status['plan_version'],
            "message": "本图当前计划已确认，其他图片的确认不变。"}


def apply_planning_result(state, kind, target, feedback, result, call_id):
    """Apply validated candidates by identity; return the existing Task event."""
    ids = reference_ids(state)
    materialize_confirmations(state)
    event = {"action": kind, "target": target, "feedback": feedback, "call_id": call_id}
    if kind in ["understand", "product"]:
        event["before"] = copy.deepcopy(state["product"])
        state["product"] = result["product"]
        state["product_version"] += 1
        if kind == "product":
            state["corrections"]["product"].append(feedback)
    if kind == "understand":
        state["references"] = result["references"]
        state["reference_versions"] = {key: 1 for key in ids}
    elif kind == "reference":
        event["before"] = copy.deepcopy(state["references"][target])
        state["references"][target] = result["reference"]
        state["reference_versions"][target] += 1
        state["corrections"]["references"].setdefault(target, []).append(feedback)
    if kind in ["understand", "replan"]:
        if kind == "replan":
            event["before"] = copy.deepcopy(state["plans"])
        state["plans"] = result["plans"]
        state["plan_context"] = {key: context_version(state, key) for key in ids}
        for key in ids:
            state['plan_versions'][key] = state['plan_versions'].get(key, 0) + 1
    elif kind == "plan":
        event["before"] = copy.deepcopy(state["plans"][target])
        state["plans"][target] = result["plan"]
        state["plan_context"][target] = context_version(state, target)
        state['plan_versions'][target] = state['plan_versions'].get(target, 0) + 1
    event["after"] = result
    apply_reports(state, result.get('fact_issues', []), call_id)
    state["confirmed"] = False
    return event


def edit_plan(state, target, plan, expected_version):
    """One explicit human revision; retain disputes and every other confirmation."""
    if target not in reference_ids(state) or target not in state['plans']:
        raise Problem('本图尚无可编辑方案。', 409)
    status = plan_status(state, target)
    if type(expected_version) is not int or expected_version != status['plan_version']:
        raise Problem('本图方案版本已改变，请刷新后再编辑。', 409)
    before = copy.deepcopy(state['plans'][target])
    materialize_confirmations(state)
    state['plans'][target] = copy.deepcopy(plan)
    state['plan_versions'][target] = status['plan_version'] + 1
    state['plan_context'][target] = context_version(state, target)
    state['plan_confirmations'].pop(target, None)
    state['confirmed'] = False
    return {'action': 'manual_plan', 'target': target, 'source': 'HUMAN_EDIT',
            'before': before, 'after': copy.deepcopy(plan), 'feedback': '',
            'plan_version': state['plan_versions'][target]}
