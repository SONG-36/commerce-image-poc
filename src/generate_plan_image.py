"""T03: independent image runs from a confirmed T02 plan; reuses the T01 client."""

from contextlib import contextmanager
from datetime import datetime, timezone
from importlib.metadata import version
import os
from pathlib import Path
import re
import threading
import time
from uuid import uuid4

from generate_image import MODELS, PARAMETERS, TIMEOUT_SECONDS, make_client
from evidence import clean_record, safe_text
from file_ops import read_json as read_json_file, safe_path, sha256, write_json_atomic
import image_review
import quick_redesign
from image_workflow.generation import GenerationIO, RunAccess, build_edit_prompt, build_prompt, execute_generation
from image_workflow.generation.request import PromptBuilders


def now():
    return datetime.now(timezone.utc).isoformat()


def write_json(path, value):
    write_json_atomic(path, value, transform=clean_record)


def read_json(path):
    return read_json_file(path)


def request_uncertain(record, status=None):
    status = status or record.get('status')
    code = (record.get('error') or {}).get('status_code')
    return bool(status in ['RUNNING', 'INTERRUPTED'] or status == 'FAILED' and record.get('api_call_attempted', False)
                and not (isinstance(code, int) and 400 <= code < 500 and code != 408))


class GenerationService:
    def __init__(self, store):
        self.store = store
        self.guard = threading.Lock()
        self.locks = {}
        self.active = set()

    def targets(self, state):
        role = "product" if state.get("mode") == "quick_redesign" else "reference"
        return [image["id"] for image in state["images"] if image["role"] == role]

    def folder(self, session_id, revision, target):
        if not isinstance(revision, int) or revision < 1 or not re.fullmatch(r"(?:product|reference)_[0-9]+", target or ""):
            raise ValueError("无效的图片任务。")
        return safe_path(self.store.folder(session_id), f'generations/{revision:06}/{target}')

    def run_folder(self, session_id, revision, target, run_id):
        if not re.fullmatch(r"[0-9]{8}T[0-9]{6}Z-[0-9a-f]{32}", run_id or ""):
            raise ValueError("无效的生成记录。")
        return safe_path(self.folder(session_id, revision, target), 'runs/' + run_id)

    def card(self, state, target):
        revision = state["revision"]
        folder = self.folder(state["id"], revision, target)
        pointer = read_json(folder / "current.json") if (folder / "current.json").is_file() else {}
        latest = pointer.get("latest_run")
        record = read_json(self.run_folder(state["id"], revision, target, latest) / "run.json") if latest else {}
        status = record.get("status", "NOT_STARTED")
        key = (state["id"], revision, target)
        with self.guard:
            active = key in self.active
        if status == "RUNNING" and not active:
            status = "INTERRUPTED"
        history = image_review.versions(self, state, target)
        successful = pointer.get("selected_run", pointer.get("last_successful_run"))
        image_url = None
        if successful:
            saved = self.run_folder(state["id"], revision, target, successful)
            if read_json(saved / "run.json").get("status") == "SUCCEEDED" and (saved / "image.png").is_file():
                image_url = f"/api/sessions/{state['id']}/generated-images/{revision}/{target}/{successful}"
        reference = next(image for image in state["images"] if image["id"] == target)
        error = record.get("error")
        return {
            "id": target, "plan": state["plans"].get(target), "confirmed_revision": revision,
            "requirements": state["inputs"]["requirements"], "product_facts": state["inputs"].get("product_facts", ""),
            "output_size": state.get("output_size", PARAMETERS["size"]),
            "style_references": [{"name": image["name"], "url": f"/api/sessions/{state['id']}/images/{image['id']}"}
                                 for image in state["images"] if state.get("mode") == "quick_redesign" and image["role"] == "reference"],
            "reference": {"name": reference["name"], "url": f"/api/sessions/{state['id']}/images/{target}"},
            "status": status, "run_id": latest, "image_url": image_url,
            "image_is_latest": bool(successful and successful == latest),
            "error": safe_text(error.get("message", "")) if error else None,
            "versions": history, "selected_run": successful, "passed_run": pointer.get("passed_run"),
            "card_revision": pointer.get("card_revision", 0), "started_at": record.get("api_started_at", record.get("started_at")),
            "operation": record.get("action", "generate_image"),
            "api_call_attempted": record.get('api_call_attempted', False),
            "request_uncertain": request_uncertain(record, status),
        }

    def operation(self, state, target, operation_id):
        """Only query a specific submitted request. A missing record never authorizes a retry."""
        if not re.fullmatch(r'[0-9a-f]{32}', operation_id):
            raise ValueError('无效的操作标识。')
        folder = self.folder(state['id'], state['revision'], target)
        for path in (folder / 'runs').glob('*/run.json'):
            record = read_json(safe_path(folder, str(path.relative_to(folder))))
            if record.get('operation_id') != operation_id:
                continue
            if record.get('session_id') != state['id'] or record.get('reference_id') != target or record.get('confirmed_revision') != state['revision']:
                raise ValueError('操作记录与本任务不一致。')
            status = record['status']
            with self.guard:
                active = (state['id'], state['revision'], target) in self.active
            if status == 'RUNNING' and not active:
                status = 'INTERRUPTED'
            error = record.get('error') or {}
            return {'operation_id': operation_id, 'run_id': record['run_id'], 'status': status,
                    'api_call_attempted': record.get('api_call_attempted', False), 'uncertain': request_uncertain(record, status),
                    'error': safe_text(error.get('message', '')), 'confirmed_revision': state['revision']}
        return {'operation_id': operation_id, 'status': 'NOT_FOUND', 'uncertain': True}

    @contextmanager
    def review_operation(self, state, target):
        """Coordinate human review with the existing image lock/activity scope.

        Review receives no lock or active-set ownership; generation, planning
        exclusion and export keep observing the same in-process state.
        """
        key = (state['id'], state['revision'], target)
        with self.guard:
            lock = self.locks.setdefault(key, threading.Lock())
        if not lock.acquire(blocking=False):
            raise ValueError('本张图片正在处理，请完成后再选择或审核。')
        with self.guard:
            self.active.add(key)
        try:
            yield
        finally:
            with self.guard:
                self.active.discard(key)
            lock.release()

    def generate(self, state, target, parent_run_id=None, feedback="", expected_revision=None, operation_id=None, auxiliary=None):
        if target not in self.targets(state):
            raise ValueError("图片不属于当前工作模式的制作任务。")
        if auxiliary is not None:
            if not parent_run_id:
                raise ValueError("辅助参考图片只用于修改已生成的当前版本。")
            auxiliary = image_review.prepare_auxiliary(auxiliary['name'], auxiliary['data'], auxiliary['purpose'])
        key = (state["id"], state["revision"], target)
        with self.guard:
            lock = self.locks.setdefault(key, threading.Lock())
        if not lock.acquire(blocking=False):
            raise ValueError("这张图片正在生成，本次没有重复调用模型。")
        if not self.store.lock.acquire(blocking=False):
            lock.release()
            raise ValueError('资料或计划正在处理，请稍候；本次未调用模型。')
        try:
            fresh = self.store.image_state(self.store.load(state['id']), target)
            if fresh['revision'] != state['revision']:
                raise ValueError('本图确认版本已改变，请刷新；本次未调用模型。')
            with self.guard:
                self.active.add(key)
        except BaseException:
            lock.release()
            raise
        finally:
            self.store.lock.release()
        try:
            task = self.folder(state['id'], state['revision'], target)
            if operation_id:
                if not re.fullmatch(r'[0-9a-f]{32}', operation_id):
                    raise ValueError('无效的操作标识。')
                for path in (task / 'runs').glob('*/run.json'):
                    previous = read_json(safe_path(task, str(path.relative_to(task))))
                    if previous.get('operation_id') == operation_id:
                        old_auxiliary = previous.get('auxiliary_reference')
                        same_auxiliary = ((old_auxiliary or {}).get('sha256'), (old_auxiliary or {}).get('purpose')) == ((auxiliary or {}).get('sha256'), (auxiliary or {}).get('purpose'))
                        if previous.get('parent_run_id') != parent_run_id or previous.get('feedback', '') != feedback or not same_auxiliary:
                            raise ValueError('操作标识已用于不同请求，请刷新后再操作。')
                        if previous['status'] not in ['SUCCEEDED', 'FAILED']:
                            raise ValueError('该请求的执行状态待确认，未重复调用模型；费用状态未知。')
                        return previous
            pointer = read_json(task / 'current.json') if (task / 'current.json').is_file() else {}
            if expected_revision is not None and expected_revision != pointer.get('card_revision', 0):
                raise ValueError('图片状态已改变，请刷新后再操作；本次未调用模型。')
            if parent_run_id:
                if parent_run_id != pointer.get('selected_run', pointer.get('last_successful_run')):
                    raise ValueError('当前选中版本已改变，请刷新后再修改。')
                image_review.image_bytes(self, state, target, parent_run_id)
            return self._generate(state, target, parent_run_id, feedback, operation_id, auxiliary)
        finally:
            with self.guard:
                self.active.discard(key)
            lock.release()

    def _generate(self, state, target, parent_run_id=None, feedback="", operation_id=None, auxiliary=None):
        # Application guards/locks stay above; only Generation execution crosses
        # this boundary. The package receives no Store, Web or Review service.
        access = RunAccess(
            card_folder=lambda: self.folder(state["id"], state["revision"], target),
            run_folder=lambda run_id: self.run_folder(state["id"], state["revision"], target, run_id),
            input_folder=lambda: self.store.folder(state["id"]),
            case_id=lambda: self.store.case_id(state),
            version_count=lambda: len(image_review.versions(self, state, target)),
            read_parent=lambda run_id: image_review.image_bytes(self, state, target, run_id))
        io = GenerationIO(
            client_factory=make_client, write_json=write_json, read_json=read_json, safe_text=safe_text,
            now=now, new_run_id=lambda: datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex,
            sdk_version=version, source_file=Path(__file__),
            t01_source_file=Path(__file__).with_name("generate_image.py"),
            quick_source_file=Path(quick_redesign.__file__), clock=time.perf_counter)
        prompts = PromptBuilders(build_prompt, build_edit_prompt, quick_redesign.build_prompt,
                                 quick_redesign.build_edit_prompt, image_review.auxiliary_prompt)
        return execute_generation(
            state, target, parent_run_id, feedback, operation_id, auxiliary,
            access=access, io=io, prompts=prompts, environment=os.environ, models=MODELS,
            defaults=PARAMETERS, quick_sizes=quick_redesign.SIZES, timeout_seconds=TIMEOUT_SECONDS)
