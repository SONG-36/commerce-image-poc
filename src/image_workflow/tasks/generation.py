"""Task image coordination: one guard/lock registry and explicit execution bindings.

Command-level checks remain in tasks.images; Run execution remains in generation.
Card/operation projections live in generation_queries. No HTTP, SDK, legacy
entry imports or second operation store are introduced here.
"""

from contextlib import contextmanager
from dataclasses import dataclass
import re
import threading
from typing import Callable, Mapping

from file_ops import safe_path
from image_workflow.generation import GenerationIO, RunAccess
from image_workflow.generation.request import PromptBuilders
from .generation_queries import generation_card, generation_operation, request_uncertain


@dataclass(frozen=True)
class GenerationRuntime:
    """Per-call existing execution inputs, not a model or scheduling framework."""

    io: GenerationIO
    prompts: PromptBuilders
    executor: Callable
    environment: Mapping
    models: tuple
    defaults: Mapping
    quick_sizes: tuple
    timeout_seconds: float


class GenerationService:
    def __init__(self, store, *, runtime, review, prepare_auxiliary,
                 uncertainty=request_uncertain, path_checker=safe_path):
        self.store = store
        self.guard = threading.Lock()
        self.locks = {}
        self.active = set()
        self._runtime = runtime
        self._review = review
        self._prepare_auxiliary = prepare_auxiliary
        self._uncertainty = uncertainty
        self._path = path_checker

    def targets(self, state):
        role = "product" if state.get("mode") == "quick_redesign" else "reference"
        return [image["id"] for image in state["images"] if image["role"] == role]

    def folder(self, session_id, revision, target):
        if not isinstance(revision, int) or revision < 1 or not re.fullmatch(r"(?:product|reference)_[0-9]+", target or ""):
            raise ValueError("无效的图片任务。")
        return self._path(self.store.folder(session_id), f'generations/{revision:06}/{target}')

    def run_folder(self, session_id, revision, target, run_id):
        if not re.fullmatch(r"[0-9]{8}T[0-9]{6}Z-[0-9a-f]{32}", run_id or ""):
            raise ValueError("无效的生成记录。")
        return self._path(self.folder(session_id, revision, target), 'runs/' + run_id)

    def card(self, state, target):
        runtime = self._runtime()
        return generation_card(self, state, target, reader=runtime.io.read_json,
                               safe_text=runtime.io.safe_text, defaults=runtime.defaults,
                               review=self._review, uncertainty=self._uncertainty)

    def operation(self, state, target, operation_id):
        runtime = self._runtime()
        return generation_operation(self, state, target, operation_id,
                                    reader=runtime.io.read_json, safe_text=runtime.io.safe_text,
                                    uncertainty=self._uncertainty, path_check=self._path)

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
            auxiliary = self._prepare_auxiliary(auxiliary['name'], auxiliary['data'], auxiliary['purpose'])
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
            read_json = self._runtime().io.read_json
            if operation_id:
                if not re.fullmatch(r'[0-9a-f]{32}', operation_id):
                    raise ValueError('无效的操作标识。')
                for path in (task / 'runs').glob('*/run.json'):
                    previous = read_json(self._path(task, str(path.relative_to(task))))
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
                self._review.image_bytes(self, state, target, parent_run_id)
            return self._generate(state, target, parent_run_id, feedback, operation_id, auxiliary)
        finally:
            with self.guard:
                self.active.discard(key)
            lock.release()

    def _generate(self, state, target, parent_run_id=None, feedback="", operation_id=None, auxiliary=None):
        runtime = self._runtime()
        access = RunAccess(
            card_folder=lambda: self.folder(state["id"], state["revision"], target),
            run_folder=lambda run_id: self.run_folder(state["id"], state["revision"], target, run_id),
            input_folder=lambda: self.store.folder(state["id"]),
            case_id=lambda: self.store.case_id(state),
            version_count=lambda: len(self._review.versions(self, state, target)),
            read_parent=lambda run_id: self._review.image_bytes(self, state, target, run_id))
        return runtime.executor(
            state, target, parent_run_id, feedback, operation_id, auxiliary,
            access=access, io=runtime.io, prompts=runtime.prompts, environment=runtime.environment,
            models=runtime.models, defaults=runtime.defaults, quick_sizes=runtime.quick_sizes,
            timeout_seconds=runtime.timeout_seconds)
