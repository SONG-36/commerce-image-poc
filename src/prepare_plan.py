"""Local T02 web page. Only explicit AI POST actions can create paid requests."""

import argparse
import copy
from datetime import datetime, timezone
from importlib.metadata import version
import io
import json
import os
from pathlib import Path
import re
import threading
import time
from uuid import uuid4

from flask import Flask, jsonify, render_template, request, send_file, redirect
from openai import OpenAI
from PIL import Image
from werkzeug.exceptions import HTTPException

from file_ops import (read_json as read_json_file, safe_path, sha256,
                      write_json_atomic, write_json_exclusive)
from generate_plan_image import GenerationService
from evidence import clean_record, safe_text, contains_private
from experiment_export import export_experiment, ExportError, historical_case_match
import image_review
from quick_redesign import DEFAULT_REQUIREMENTS, SIZES
from persistence import task_state
from image_workflow import Problem
from image_workflow.planning import (RULES, PRODUCT_FIELDS, REFERENCE_FIELDS, PLAN_FIELDS,
                                     fields, reference_ids, response_shape,
                                     planning_images, validate_result)
from image_workflow.planning.request import build_planning_request as _build_planning_request
from image_workflow.planning.service import PlanningIO, execute_planning

ROOT = Path(__file__).resolve().parents[1]
# Model policy remains literal: the existing deploy preflight reads it via AST.
MODELS = ("gpt-5.4-mini", "gpt-4.1-mini", "gpt-4.1-mini-2025-04-14")


def now():
    return datetime.now(timezone.utc).isoformat()


def write_json(path, value, exclusive=False):
    if exclusive:
        write_json_exclusive(path, value, transform=clean_record)
    else:
        write_json_atomic(path, value, transform=clean_record)


def read_json(path):
    return read_json_file(path)


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
    return {'plan_version': version, 'confirmed': current, 'confirmation': entry, 'legacy': legacy}


def materialize_confirmations(state):
    """Only on an explicit write: retain legacy confirmations before changing a plan."""
    statuses = {target: plan_status(state, target) for target in reference_ids(state)}
    state['plan_versions'] = {target: item['plan_version'] for target, item in statuses.items()}
    state['plan_confirmations'] = {target: copy.deepcopy(item['confirmation']) for target, item in statuses.items() if item['confirmation']}


class Store:
    def __init__(self, root, case_dir=None):
        self.root = Path(root)
        self.case_dir = Path(case_dir) if case_dir else None
        self.lock = threading.Lock()
        self.planning = {}

    def case_id(self, state):
        if state.get("case_id"):
            return state["case_id"]
        if self.case_dir and historical_case_match(state, self.folder(state["id"]), self.case_dir):
            return "case-001"
        return "case-" + state["id"]

    def folder(self, session_id):
        if not re.fullmatch(r"[0-9a-f]{32}", session_id or ""):
            raise Problem("无效的任务标识。", 404)
        return safe_path(self.root, 'sessions/' + session_id)

    def load(self, session_id):
        try:
            state = task_state.read_current(self.folder(session_id), reader=read_json)
        except task_state.MissingStateFile:
            raise Problem("准备任务不存在，请重新加载资料。", 404) from None
        if state.get('id') != session_id:
            raise Problem('任务标识与保存记录不一致。', 409)
        for image in state['images']:
            if not re.fullmatch(r'inputs/(?:product|reference)_[0-9]+\.(?:jpg|jpeg|png|webp)', image['file']):
                raise Problem('任务图片路径不在本任务允许范围内。', 409)
            safe_path(self.folder(session_id), image['file'])
        return state

    def save(self, state, event):
        state["revision"] += 1
        if state.get('plan_confirmations'):
            state['confirmed'] = all(plan_status(state, target)['confirmed'] for target in reference_ids(state))
        state["updated_at"] = now()
        state["events"].append({"at": now(), "revision": state["revision"], **event})
        task_state.write_snapshot_and_current(self.folder(state["id"]), state, writer=write_json)

    def version(self, state, revision):
        if not isinstance(revision, int) or not 1 <= revision <= state['revision']:
            raise Problem('图片确认版本无效。', 409)
        try:
            saved = task_state.read_snapshot(self.folder(state['id']), revision, reader=read_json)
        except task_state.MissingStateFile:
            raise Problem('本任务的确认版本记录不存在。', 409) from None
        if saved.get('id') != state['id'] or saved.get('revision') != revision:
            raise Problem('历史计划记录与本任务不一致，已停止读取。', 409)
        return saved

    def image_state(self, state, target, required=True):
        if state.get('mode') == 'quick_redesign':
            return state
        status = plan_status(state, target)
        if required and not status['confirmed']:
            raise Problem('请先确认本图当前版本的计划；本次未调用模型。', 409)
        entry = status['confirmation']
        if not entry:
            return state
        saved = self.version(state, entry['revision'])
        if target not in reference_ids(saved) or saved['plans'].get(target) is None:
            raise Problem('本图确认快照不完整。', 409)
        if sha256(json.dumps(saved['plans'][target], ensure_ascii=False, sort_keys=True).encode()) != entry['plan_sha256']:
            raise Problem('本图确认快照与计划不一致。', 409)
        if context_version(saved, target) != entry['context']:
            raise Problem('本图确认快照与理解版本不一致。', 409)
        return saved

    def image_history(self, state, target):
        """Read immutable, task-scoped plan buckets without migrating existing runs."""
        directory = safe_path(self.folder(state['id']), 'generations')
        for folder in sorted(directory.iterdir(), reverse=True) if directory.is_dir() else []:
            if not re.fullmatch(r'[0-9]{6}', folder.name) or not (folder / target).is_dir():
                continue
            saved = self.version(state, int(folder.name))
            if target in reference_ids(saved) or saved.get('mode') == 'quick_redesign' and target in [i['id'] for i in saved['images'] if i['role'] == 'product']:
                yield saved

    def card_view(self, generation, state, target):
        quick = state.get('mode') == 'quick_redesign'
        status = None if quick else plan_status(state, target)
        current = self.image_state(state, target, required=False)
        card = generation.card(current, target)
        history = [generation.card(saved, target) for saved in self.image_history(state, target)]
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

    def create(self, text, uploads, title, case_id=None, mode="product_pack", output_size="1024x1536"):
        if mode not in ("product_pack", "quick_redesign"):
            raise Problem("请选择有效的工作模式。")
        if mode == "quick_redesign" and output_size not in SIZES:
            raise Problem("请选择支持的输出比例。")
        if not any(role == "product" for role, _, _ in uploads):
            raise Problem("请至少提供一张商品原图。")
        if mode == "product_pack" and not any(role == "reference" for role, _, _ in uploads):
            raise Problem("请至少提供一张商品原图和一张设计参考图。")
        if any(not isinstance(text.get(key), str) for key in ["listing", "description", "requirements"]):
            raise Problem("资料文本格式不正确。")
        if mode == "quick_redesign":
            if not isinstance(text.get("product_facts", ""), str):
                raise Problem("商品事实说明格式不正确。")
            if contains_private(text):
                raise Problem("资料包含疑似认证信息，请移除后重新保存；未发送模型。")
            text = {**text, "requirements": text["requirements"].strip() or DEFAULT_REQUIREMENTS,
                    "product_facts": text.get("product_facts", "")}
        checked = []
        for role, name, data in uploads:
            if len(data) > 20 * 1024 * 1024:
                raise Problem("单张图片不能超过 20 MB。")
            try:
                with Image.open(io.BytesIO(data)) as image:
                    ext, mime = {"JPEG": ("jpg", "image/jpeg"), "PNG": ("png", "image/png"), "WEBP": ("webp", "image/webp")}[image.format]
                    width, height = image.size
                    image.verify()
                with Image.open(io.BytesIO(data)) as image:
                    image.load()
            except Exception as error:
                raise Problem("无法读取上传图片，请使用有效的 JPG、PNG 或 WebP。") from error
            checked.append((role, Path(name).name, data, ext, mime, width, height))
        session_id = uuid4().hex
        folder = self.folder(session_id)
        (folder / "inputs").mkdir(parents=True)
        state = {
            "id": session_id, "title": title, "created_at": now(), "revision": 0,
            "mode": mode, "output_size": output_size,
            "case_id": case_id or "case-" + session_id,
            "inputs": text, "images": [], "product": None, "references": {}, "plans": {},
            "product_version": 0, "reference_versions": {}, "plan_context": {},
            "corrections": {"product": [], "references": {}}, "events": [], "confirmed": False,
        }
        counts = {"product": 0, "reference": 0}
        for role, name, data, ext, mime, width, height in checked:
            counts[role] += 1
            image_id = f"{role}_{counts[role]:03}"
            relative = f"inputs/{image_id}.{ext}"
            with (folder / relative).open("xb") as stream:
                stream.write(data)
            state["images"].append({"id": image_id, "role": role, "name": name, "file": relative,
                                    "mime": mime, "sha256": sha256(data), "bytes": len(data), "width": width, "height": height})
        write_json(folder / "inputs" / "texts.json", text, exclusive=True)
        self.save(state, {"action": "inputs_saved", "feedback": "", "target": None})
        write_json(self.root / "current.json", {"id": session_id})
        return state


def build_planning_request(state, action, target, feedback, model, image_bytes):
    """Compatibility entry: model policy stays explicit for pure construction."""
    return _build_planning_request(state, action, target, feedback, model, image_bytes,
                                   reasoning_model=MODELS[0], instructions=RULES)


def call_ai(store, state, action, target, feedback):
    """Adapt legacy Store/config/mock seams to the independent Planning use case."""
    return execute_planning(
        store.folder(state["id"]), state, action, target, feedback,
        case_id_for=store.case_id, activity=store.planning, models=MODELS, environment=os.environ,
        io=PlanningIO(client_factory=OpenAI, write_json=write_json, safe_text=safe_text,
                      now=now, new_id=uuid4, sdk_version=version, source_file=Path(__file__),
                      clock=time.perf_counter),
        request_builder=build_planning_request, validator=validate_result, instructions=RULES)


def create_app(runtime_dir=None, case_dir=None):
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 80 * 1024 * 1024
    app.config["MAX_FORM_MEMORY_SIZE"] = 2 * 1024 * 1024
    case = Path(case_dir or ROOT / ".runtime/inputs/case-001")
    store = Store(runtime_dir or ROOT / ".runtime/prepare-plan", case)
    generation = GenerationService(store)
    app.extensions["plan_store"] = store
    app.extensions["generation_service"] = generation

    @app.before_request
    def local_action():
        if request.method == "POST":
            if request.headers.get("Origin") and request.headers["Origin"] != request.host_url.rstrip("/"):
                raise Problem("仅接受当前页面提交的操作。", 403)
            if request.headers.get("X-Local-Action") != "prepare-plan":
                raise Problem("请从准备与规划页面执行操作。", 403)

    @app.errorhandler(Problem)
    def problem(error):
        return jsonify(error=safe_text(str(error))), error.status

    @app.errorhandler(HTTPException)
    def http_problem(error):
        return jsonify(error="上传体积过大，请减少图片或文件大小。" if error.code == 413 else error.description), error.code

    @app.errorhandler(ExportError)
    def unsafe_path(error):
        return jsonify(error=safe_text(str(error))), 409

    def activity(state):
        active = store.planning.get(state['id'])
        if active:
            result = {key: active.get(key) for key in ['action','status','started_at','api_call_attempted','id']}
            result['status'] = 'RUNNING'
        else:
            calls = [read_json(path) for path in store.folder(state['id']).glob('calls/*/run.json')]
            latest = max(calls, key=lambda call: call['started_at']) if calls else None
            result = {key: latest.get(key) for key in ['action','status','started_at','finished_at','elapsed_seconds','api_call_attempted','id']} if latest else None
            if latest and latest['status'] in ['RUNNING','PREPARING']:
                result['status'] = 'INTERRUPTED'
        return result

    def public(state):
        result = copy.deepcopy(state)
        result["mode"] = state.get("mode", "product_pack")
        result["stale_plans"] = stale_ids(state)
        result['plan_status'] = {target: plan_status(state, target) for target in reference_ids(state)}
        for image in result["images"]:
            image["url"] = f"/api/sessions/{state['id']}/images/{image['id']}"
        return result

    @app.get("/")
    def home():
        legacy = request.args.get('session')
        if legacy:
            store.load(legacy)
            return redirect('/prepare/' + legacy)
        return render_template('tasks.html')

    @app.get('/workspace/new')
    @app.get('/prepare/new')
    def new_task_page():
        return render_template('prepare.html', session_id='')

    @app.get('/workspace/<session_id>')
    @app.get('/prepare/<session_id>')
    def prepare_page(session_id):
        store.load(session_id)
        return render_template('prepare.html', session_id=session_id)

    @app.get('/api/tasks')
    def task_list():
        tasks = []
        sessions = safe_path(store.root, 'sessions')
        for folder in sorted(sessions.iterdir()) if sessions.is_dir() else []:
            if not re.fullmatch(r'[0-9a-f]{32}', folder.name):
                continue
            state = store.load(folder.name)
            quick = state.get('mode') == 'quick_redesign'
            cards = [store.card_view(generation, state, target) for target in generation.targets(state)]
            generated = sum(card['has_generated_history'] for card in cards)
            passed = sum(card['has_passed_history'] for card in cards)
            total = len(generation.targets(state))
            if state['id'] in store.planning:
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
        return jsonify(tasks=tasks)

    def confirmed_state(session_id, target=None):
        state = store.load(session_id)
        if target is not None and target not in generation.targets(state):
            raise Problem('指定图片计划不存在。', 404)
        if state.get("mode") == "quick_redesign":
            if not generation.targets(state) or state.get("output_size") not in SIZES:
                raise Problem("重设计任务的原图或输出比例无效。", 409)
            return state
        if target is not None:
            if target not in generation.targets(state):
                raise Problem('指定图片计划不存在。', 404)
            return store.image_state(state, target)
        return state

    def generation_view(state):
        return {'session_id': state['id'], 'title': state['title'], 'mode': state.get('mode', 'product_pack'),
                'confirmed_revision': state['revision'], 'auxiliary_purposes': image_review.AUXILIARY_PURPOSES,
                'auxiliary_max_bytes': image_review.MAX_AUXILIARY_BYTES,
                'cards': [store.card_view(generation, state, target) for target in generation.targets(state)]}

    @app.get("/generate/<session_id>")
    def generate_page(session_id):
        store.load(session_id)
        return render_template("generate.html", session_id=session_id)

    @app.get('/api/sessions/<session_id>/workspace')
    def workspace_state(session_id):
        """Read current planning plus scoped image history; never mutate or call AI."""
        state = store.load(session_id)
        view = generation_view(state)
        return jsonify(state=public(state), activity=activity(state), ai_configured=bool(os.environ.get('OPENAI_API_KEY', '')),
                       generation_allowed=any(card['generation_allowed'] for card in view['cards']),
                       historical_generation=any(card['historical_generation'] for card in view['cards']), generation=view)

    @app.post("/api/sessions/<session_id>/export-experiment")
    def export_case(session_id):
        store.folder(session_id)  # Validate the identifier before filesystem access.
        try:
            if not store.lock.acquire(blocking=False):
                raise Problem("理解或规划尚在处理中，请完成后再导出。", 409)
            try:
                with generation.guard:
                    if any(key[0] == session_id for key in generation.active):
                        raise Problem("当前任务有图片正在生成，请完成后再导出。", 409)
                    package, filename = export_experiment(store, session_id)
            finally:
                store.lock.release()
        except (ExportError, OSError, KeyError, TypeError) as error:
            raise Problem(str(error) if isinstance(error, ExportError) else "实验包导出失败：允许范围内的证据缺失或不可读取；原文件未改动。", 409) from error
        return send_file(package, mimetype="application/zip", as_attachment=True, download_name=filename, max_age=0)

    @app.get("/api/sessions/<session_id>/generation")
    def generation_state(session_id):
        state = confirmed_state(session_id)
        return jsonify(generation_view(state))

    @app.post('/api/sessions/<session_id>/review/<target>')
    def review_one(session_id, target):
        state = confirmed_state(session_id, target)
        body = request.get_json()
        if target not in generation.targets(state) or not isinstance(body, dict) or body.get('confirmed_revision') != state['revision']:
            raise Problem('任务、图片或确认计划已改变，请刷新。', 409)
        try:
            event = image_review.review(generation, state, target, body.get('action'), body.get('run_id'), body.get('card_revision'))
        except (ValueError, OSError) as error:
            raise Problem(safe_text(str(error)), 409) from error
        return jsonify(event=event)

    @app.post('/api/sessions/<session_id>/revise/<target>')
    def revise_one(session_id, target):
        state = confirmed_state(session_id, target)
        if store.card_view(generation, store.load(session_id), target)['request_uncertain']:
            raise Problem('本图存在运行中或结果不确定的请求，请先人工核对；未重新调用模型。', 409)
        multipart = request.mimetype == 'multipart/form-data'
        body = request.form.to_dict() if multipart else request.get_json()
        if multipart:
            try:
                for key in ('confirmed_revision', 'card_revision'):
                    body[key] = int(body[key])
            except (KeyError, ValueError) as error:
                raise Problem('图片版本信息无效，请刷新后重新修改。') from error
        elif isinstance(body, dict) and any(key in body for key in ('auxiliary', 'auxiliary_reference', 'auxiliary_path', 'auxiliary_purpose')):
            raise Problem('辅助图片必须随本次修改上传实际文件，不能使用路径或其他任务的图片标识。')
        if target not in generation.targets(state) or not isinstance(body, dict) or body.get('confirmed_revision') != state['revision']:
            raise Problem('任务、图片或确认计划已改变，请刷新；未调用模型。', 409)
        feedback = body.get('feedback')
        if not isinstance(feedback, str) or not feedback.strip() or len(feedback) > 12000 or not body.get('parent_run_id') or not body.get('operation_id') or not isinstance(body.get('card_revision'), int):
            raise Problem('请选择当前版本并填写修改意见（最多 12000 字）。')
        auxiliary = None
        if multipart:
            uploads = [(name, file) for name in request.files for file in request.files.getlist(name)]
            if len(uploads) > 1 or any(name != 'auxiliary' for name, _ in uploads):
                raise Problem('每次修改最多新增一张辅助参考图片。')
            if uploads:
                file = uploads[0][1]
                try:
                    auxiliary = image_review.prepare_auxiliary(file.filename, file.read(image_review.MAX_AUXILIARY_BYTES + 1), body.get('auxiliary_purpose'))
                except ValueError as error:
                    raise Problem(str(error)) from error
            elif body.get('auxiliary_purpose'):
                raise Problem('请选择本次辅助图片，或清除辅助图片用途后仅用文字修改。')
        try:
            record = generation.generate(state, target, body['parent_run_id'], feedback, body['card_revision'], body['operation_id'], auxiliary=auxiliary)
        except ValueError as error:
            raise Problem(str(error), 409) from error
        return generation_result(record)

    @app.post('/api/sessions/<session_id>/export-passed')
    def passed_images(session_id):
        state = confirmed_state(session_id)
        try:
            with generation.guard:
                if any(key[0] == session_id for key in generation.active):
                    raise ValueError('任务有图片正在处理，请完成后再导出。')
                package, filename = image_review.export_passed(generation, state)
        except (ValueError, OSError) as error:
            raise Problem(str(error), 409) from error
        return send_file(package, mimetype='application/zip', as_attachment=True, download_name=filename, max_age=0)

    def generation_result(record):
        if record['status'] == 'FAILED':
            message = safe_text(record['error']['message'])
            if record['api_call_attempted']:
                message += '；服务端是否执行或计费尚未确认，未自动重试，已保留之前成功的图片。'
            return jsonify(error=message, run_id=record['run_id'], confirmed_revision=record['confirmed_revision']), 502 if record['api_call_attempted'] else 400
        return jsonify(run_id=record['run_id'], confirmed_revision=record['confirmed_revision'], status='SUCCEEDED')

    @app.post("/api/sessions/<session_id>/generate/<target>")
    def generate_one(session_id, target):
        latest = store.load(session_id)
        state = confirmed_state(session_id, target)
        if store.card_view(generation, latest, target)['request_uncertain']:
            raise Problem('本图存在运行中或结果不确定的请求，请先人工核对；未重新调用模型。', 409)
        body = request.get_json()
        if not isinstance(body, dict) or body.get("confirmed_revision") != state["revision"]:
            raise Problem("确认计划的版本已改变，请刷新页面；本次没有调用模型。", 409)
        if target not in generation.targets(state):
            raise Problem("指定图片计划不存在。", 404)
        if state.get("mode") == "quick_redesign" and (not isinstance(body.get("card_revision"), int) or not body.get("operation_id")):
            raise Problem("请刷新图片状态后再提交；本次未调用模型。", 409)
        if body.get('batch_only'):
            if not body.get('operation_id') or not isinstance(body.get('card_revision'), int) or not store.card_view(generation, latest, target)['batch_eligible']:
                raise Problem('本图不再符合批量条件，已生成、已尝试、已 Pass 或状态待确认；未调用模型。', 409)
        try:
            record = generation.generate(state, target, expected_revision=body.get('card_revision'), operation_id=body.get('operation_id'))
        except ValueError as error:
            raise Problem(str(error), 409) from error
        return generation_result(record)

    @app.get('/api/sessions/<session_id>/operations/<target>/<operation_id>')
    def operation_status(session_id, target, operation_id):
        state = store.load(session_id)
        if target not in generation.targets(state):
            raise Problem('图片不属于当前任务。', 404)
        try:
            revision = int(request.args.get('confirmed_revision', ''))
            snapshot = store.version(state, revision)
            if target not in generation.targets(snapshot):
                raise Problem('图片不属于请求版本。', 404)
            return jsonify(generation.operation(snapshot, target, operation_id))
        except ValueError as error:
            raise Problem(str(error), 400) from error

    @app.get("/api/sessions/<session_id>/generated-images/<int:revision>/<target>/<run_id>")
    def generated_image(session_id, revision, target, run_id):
        store.load(session_id)
        try:
            folder = generation.run_folder(session_id, revision, target, run_id)
        except ValueError as error:
            raise Problem(str(error), 404) from error
        if not (folder / "run.json").is_file() or read_json(folder / "run.json").get("status") != "SUCCEEDED":
            raise Problem("成功生成的图片不存在。", 404)
        try:
            image_state = store.load(session_id)
            image_state['revision'] = revision
            data, _ = image_review.image_bytes(generation, image_state, target, run_id)
        except (ValueError, OSError) as error:
            raise Problem(str(error), 409) from error
        return send_file(io.BytesIO(data), mimetype="image/png")

    @app.get("/api/current")
    def current():
        path = store.root / "current.json"
        state = store.load(read_json(path)["id"]) if path.is_file() else None
        return jsonify(state=public(state) if state else None, activity=activity(state) if state else None, ai_configured=bool(os.environ.get("OPENAI_API_KEY", "")))

    @app.get("/api/sessions/<session_id>")
    def saved_session(session_id):
        state = store.load(session_id)
        return jsonify(state=public(state), activity=activity(state), ai_configured=bool(os.environ.get("OPENAI_API_KEY", "")))

    @app.get("/api/sessions/<session_id>/images/<image_id>")
    def image_file(session_id, image_id):
        state = store.load(session_id)
        image = next((image for image in state["images"] if image["id"] == image_id), None)
        if not image:
            raise Problem("图片不存在。", 404)
        path = safe_path(store.folder(session_id), image['file'])
        if sha256(path.read_bytes()) != image['sha256']:
            raise Problem('图片与本任务保存的记录不一致。', 409)
        return send_file(path, mimetype=image["mime"])

    @app.post("/api/case-001")
    def load_case():
        with store.lock:
            text = {"listing": (case / "listing.md").read_text(encoding="utf-8"),
                    "description": "", "requirements": (case / "requirements.md").read_text(encoding="utf-8")}
            uploads = [(role, path.name, path.read_bytes()) for role, folder in [("product", "product"), ("reference", "references")]
                       for path in sorted((case / folder).iterdir()) if path.is_file() and path.suffix.lower() in [".jpg", ".jpeg", ".png", ".webp"]]
            state = store.create(text, uploads, "case-001", case_id="case-001")
            return jsonify(state=public(state))

    @app.post("/api/sessions")
    def save_inputs():
        with store.lock:
            uploads = []
            previous_id = request.form.get("from_session")
            if previous_id:
                previous = store.load(previous_id)
                try:
                    keep = json.loads(request.form.get("keep_images", "[]"))
                except json.JSONDecodeError as error:
                    raise Problem("保留图片列表无效。") from error
                if not isinstance(keep, list) or not set(keep).issubset({image["id"] for image in previous["images"]}):
                    raise Problem("保留图片列表无效。")
                for image in previous["images"]:
                    if image["id"] in keep:
                        uploads.append((image["role"], image["name"], (store.folder(previous_id) / image["file"]).read_bytes()))
            for role in ["product", "reference"]:
                uploads.extend((role, file.filename, file.read()) for file in request.files.getlist(role) if file.filename)
            mode = request.form.get("mode", "product_pack")
            if previous_id and mode != previous.get("mode", "product_pack"):
                raise Problem("复制任务不能切换工作模式；请从任务中心新建。")
            keys = ["listing", "description", "requirements"] + (["product_facts"] if mode == "quick_redesign" else [])
            text = {key: request.form.get(key, "") for key in keys}
            title = request.form.get('title', '新商品资料').strip()
            if not title or len(title) > 120:
                raise Problem('请填写任务名称（最多 120 字）。')
            state = store.create(text, uploads, title, mode=mode, output_size=request.form.get("output_size", "1024x1536"))
            return jsonify(state=public(state))

    @app.post("/api/sessions/<session_id>/action")
    def action(session_id):
        if not store.lock.acquire(blocking=False):
            raise Problem("有操作正在处理，请稍候；本次没有重复调用模型。", 409)
        try:
            with generation.guard:
                if any(key[0] == session_id for key in generation.active):
                    raise Problem('本任务有图片正在处理，请完成后再改动或确认计划。', 409)
            state = store.load(session_id)
            if state.get("mode") == "quick_redesign":
                raise Problem("快速重设计不执行商品理解或规划；请进入图片生成。", 409)
            body = request.get_json()
            if not isinstance(body, dict) or body.get("revision") != state["revision"]:
                raise Problem("页面内容已过期，请刷新后再操作；本次没有调用模型。", 409)
            kind, target, feedback = body.get("action"), body.get("target"), body.get("feedback", "")
            ids = reference_ids(state)
            if kind not in ["understand", "product", "reference", "plan", "replan", "confirm"]:
                raise Problem("不支持的操作。")
            if kind != "understand" and state["product"] is None:
                raise Problem("请先完成 AI 理解与规划。")
            if kind in ["reference", "plan"] and target not in ids:
                raise Problem("指定参考图或计划不存在。")
            if not isinstance(feedback, str) or len(feedback) > 12000 or kind in ["product", "reference", "plan"] and not feedback.strip():
                raise Problem("请填写本次修改意见（最多 12000 字）。")
            if kind == "understand" and state["product"] is not None:
                raise Problem("已有理解与计划，请使用修正或重新规划按钮，避免覆盖修改。")
            if kind == "confirm":
                if target not in ids or target not in state['plans'] or target in stale_ids(state):
                    raise Problem('请在对应卡片确认已采用最新理解的本图计划。')
                status = plan_status(state, target)
                if body.get('plan_version', status['plan_version']) != status['plan_version']:
                    raise Problem('本图计划版本已改变，请刷新后确认。', 409)
                if status['confirmed']:
                    return jsonify(state=public(state))
                materialize_confirmations(state)
                state['plan_confirmations'][target] = {
                    'plan_version': status['plan_version'], 'revision': state['revision'] + 1,
                    'plan_sha256': sha256(json.dumps(state['plans'][target], ensure_ascii=False, sort_keys=True).encode()),
                    'context': context_version(state, target), 'confirmed_at': now()}
                state['plan_confirmations'][target]['source'] = 'EXPLICIT_PER_IMAGE'
                store.save(state, {"action": "confirm", "target": target, "feedback": "", "plan_version": status['plan_version'],
                                   "message": "本图当前计划已确认，其他图片的确认不变。"})
                return jsonify(state=public(state))
            parent_revision = state["revision"]
            result, call_id = call_ai(store, state, kind, target, feedback)
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
            state["confirmed"] = False
            store.save(state, event)
            write_json(store.folder(session_id) / "calls" / call_id / "applied.json",
                       {"revision": state["revision"], "parent_revision": parent_revision, "run_id": call_id,
                        "case_id": store.case_id(state), "version_file": f"versions/{state['revision']:06}.json", "at": now()}, exclusive=True)
            return jsonify(state=public(state))
        finally:
            store.lock.release()

    return app


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8010)
    args = parser.parse_args()
    create_app().run(host="127.0.0.1", port=args.port, debug=False)
