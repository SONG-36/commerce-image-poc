"""Read-only Task/confirmation queries and front-end projections.

Image summaries are supplied by the application peer's public card/targets
methods. No query writes state, takes ownership of locks or invokes a model.
"""

import copy
import json
import re

from file_ops import safe_path, sha256
from image_workflow import Problem
from image_workflow.planning.request import reference_ids
from persistence import task_state
from .rules import context_version, plan_status, stale_ids


def case_identifier(store, state, case_match):
    if state.get("case_id"):
        return state["case_id"]
    if store.case_dir and case_match(state, store.folder(state["id"]), store.case_dir):
        return "case-001"
    return "case-" + state["id"]


def version(store, state, revision):
    if not isinstance(revision, int) or not 1 <= revision <= state['revision']:
        raise Problem('图片确认版本无效。', 409)
    try:
        saved = store.read_snapshot(state['id'], revision)
    except task_state.MissingStateFile:
        raise Problem('本任务的确认版本记录不存在。', 409) from None
    if saved.get('id') != state['id'] or saved.get('revision') != revision:
        raise Problem('历史计划记录与本任务不一致，已停止读取。', 409)
    return saved


def image_state(store, state, target, required=True):
    if state.get('mode') == 'quick_redesign':
        return state
    status = plan_status(state, target)
    if required and not status['confirmed']:
        raise Problem('请先确认本图当前版本的计划；本次未调用模型。', 409)
    entry = status['confirmation']
    if not entry:
        return state
    saved = store.version(state, entry['revision'])
    if target not in reference_ids(saved) or saved['plans'].get(target) is None:
        raise Problem('本图确认快照不完整。', 409)
    if sha256(json.dumps(saved['plans'][target], ensure_ascii=False, sort_keys=True).encode()) != entry['plan_sha256']:
        raise Problem('本图确认快照与计划不一致。', 409)
    if context_version(saved, target) != entry['context']:
        raise Problem('本图确认快照与理解版本不一致。', 409)
    return saved


def image_history(store, state, target):
    """Read immutable, task-scoped plan buckets without migrating existing runs."""
    directory = safe_path(store.folder(state['id']), 'generations')
    for folder in sorted(directory.iterdir(), reverse=True) if directory.is_dir() else []:
        if not re.fullmatch(r'[0-9]{6}', folder.name) or not (folder / target).is_dir():
            continue
        saved = store.version(state, int(folder.name))
        if target in reference_ids(saved) or saved.get('mode') == 'quick_redesign' and target in [i['id'] for i in saved['images'] if i['role'] == 'product']:
            yield saved


def card_view(store, card_reader, state, target):
    quick = state.get('mode') == 'quick_redesign'
    status = None if quick else plan_status(state, target)
    current = image_state(store, state, target, required=False)
    card = card_reader(current, target)
    history = [card_reader(saved, target) for saved in image_history(store, state, target)]
    older = next((old for old in history if old['versions'] and old['confirmed_revision'] != current['revision']), None)
    allowed = quick or status['confirmed']
    historical = False
    if not allowed and older and not card['versions']:
        card = copy.deepcopy(older)
        historical = True
    elif not allowed and card['versions']:
        historical = True
    elif older and not card['versions']:
        card['previous_result'] = {'revision': older['confirmed_revision'], 'image_url': older['image_url']}
    has_history = bool(card['versions'] or any(old['versions'] for old in history))
    passed = next((old for old in history if old['passed_run']), None)
    attempted = any(old['run_id'] for old in history)
    card.update(generation_allowed=allowed, historical_generation=historical,
                generation_revision=current['revision'], plan_status=status,
                has_generated_history=has_history, has_passed_history=bool(passed),
                request_uncertain=card['request_uncertain'] or any(old['request_uncertain'] for old in history))
    if passed:
        card['accepted_result'] = {'revision': passed['confirmed_revision'], 'run_id': passed['passed_run']}
    card['batch_eligible'] = bool(allowed and not has_history and not passed and not attempted and card['status'] == 'NOT_STARTED')
    return card


class TaskQueries:
    def __init__(self, store, generation, *, auxiliary_purposes, auxiliary_max_bytes, quick_sizes):
        self.store = store
        self.generation = generation
        self.auxiliary_purposes = auxiliary_purposes
        self.auxiliary_max_bytes = auxiliary_max_bytes
        self.quick_sizes = quick_sizes

    def card_view(self, state, target):
        return card_view(self.store, self.generation.card, state, target)

    def activity(self, state):
        active = self.store.planning.get(state['id'])
        if active:
            result = {key: active.get(key) for key in ['action','status','started_at','api_call_attempted','id']}
            result['status'] = 'RUNNING'
        else:
            calls = [self.store.read_json(path) for path in self.store.folder(state['id']).glob('calls/*/run.json')]
            latest = max(calls, key=lambda call: call['started_at']) if calls else None
            result = {key: latest.get(key) for key in ['action','status','started_at','finished_at','elapsed_seconds','api_call_attempted','id']} if latest else None
            if latest and latest['status'] in ['RUNNING','PREPARING']:
                result['status'] = 'INTERRUPTED'
        return result

    def public(self, state):
        result = copy.deepcopy(state)
        result["mode"] = state.get("mode", "product_pack")
        result["stale_plans"] = stale_ids(state)
        result['plan_status'] = {target: plan_status(state, target) for target in reference_ids(state)}
        for image in result["images"]:
            image["url"] = f"/api/sessions/{state['id']}/images/{image['id']}"
        return result

    def task_list(self):
        tasks = []
        sessions = safe_path(self.store.root, 'sessions')
        for folder in sorted(sessions.iterdir()) if sessions.is_dir() else []:
            if not re.fullmatch(r'[0-9a-f]{32}', folder.name):
                continue
            state = self.store.load(folder.name)
            quick = state.get('mode') == 'quick_redesign'
            cards = [self.card_view(state, target) for target in self.generation.targets(state)]
            generated = sum(card['has_generated_history'] for card in cards)
            passed = sum(card['has_passed_history'] for card in cards)
            total = len(self.generation.targets(state))
            if state['id'] in self.store.planning:
                status = 'AI 理解或规划正在执行'
            elif cards and any(card['status'] == 'RUNNING' for card in cards):
                status = '图片正在处理'
            elif passed and passed == total:
                status = '新版本待审核，已有通过版本' if any(c['selected_run'] != c['passed_run'] for c in cards) else '全部图片已 Pass'
            elif generated:
                status = '图片待审核'
            elif quick or any(card['generation_allowed'] for card in cards):
                status = '资料已保存，待重设计' if quick else '部分或全部计划已确认，待生图'
            elif state.get('product'):
                status = '计划待确认'
            else:
                status = '资料已保存，待规划'
            tasks.append({'id': state['id'], 'title': state['title'], 'created_at': state['created_at'], 'mode': state.get('mode', 'product_pack'),
                          'status': status, 'generated': generated, 'passed': passed, 'total': total,
                          'url': '/workspace/' + state['id']})
        tasks.sort(key=lambda task: task['created_at'], reverse=True)
        return tasks

    def confirmed_state(self, session_id, target=None):
        state = self.store.load(session_id)
        if target is not None and target not in self.generation.targets(state):
            raise Problem('指定图片计划不存在。', 404)
        if state.get("mode") == "quick_redesign":
            if not self.generation.targets(state) or state.get("output_size") not in self.quick_sizes:
                raise Problem("重设计任务的原图或输出比例无效。", 409)
            return state
        if target is not None:
            if target not in self.generation.targets(state):
                raise Problem('指定图片计划不存在。', 404)
            return self.store.image_state(state, target)
        return state

    def generation_view(self, state):
        return {'session_id': state['id'], 'title': state['title'], 'mode': state.get('mode', 'product_pack'),
                'confirmed_revision': state['revision'], 'auxiliary_purposes': self.auxiliary_purposes,
                'auxiliary_max_bytes': self.auxiliary_max_bytes,
                'cards': [self.card_view(state, target) for target in self.generation.targets(state)]}

    def workspace(self, session_id):
        state = self.store.load(session_id)
        view = self.generation_view(state)
        return {'state': self.public(state), 'activity': self.activity(state),
                'generation_allowed': any(card['generation_allowed'] for card in view['cards']),
                'historical_generation': any(card['historical_generation'] for card in view['cards']), 'generation': view}

    def image_file(self, session_id, image_id):
        state = self.store.load(session_id)
        image = next((image for image in state["images"] if image["id"] == image_id), None)
        if not image:
            raise Problem("图片不存在。", 404)
        path = safe_path(self.store.folder(session_id), image['file'])
        if sha256(path.read_bytes()) != image['sha256']:
            raise Problem('图片与本任务保存的记录不一致。', 409)
        return path, image["mime"]
