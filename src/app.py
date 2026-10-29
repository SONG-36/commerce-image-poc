"""Application composition root. Only explicit AI POST actions create paid requests."""

import argparse
from datetime import datetime, timezone
from importlib.metadata import version
import os
from pathlib import Path
import threading
import time
from uuid import uuid4

from flask import Flask
from openai import OpenAI

from file_ops import (read_json as read_json_file, safe_path, sha256,
                      write_json_atomic, write_json_exclusive)
from image_workflow.tasks.generation_runtime import GenerationService
from infrastructure.evidence import clean_record, safe_text, contains_private
from image_workflow.experiment_export import export_experiment, ExportError, historical_case_match
from image_workflow.tasks import review as image_review
from image_workflow.generation import auxiliary
from image_workflow.generation.quick_prompt import DEFAULT_REQUIREMENTS, SIZES
from persistence import task_state
from image_workflow import Problem
from image_workflow.planning import (RULES, PRODUCT_FIELDS, REFERENCE_FIELDS, PLAN_FIELDS,
                                     fields, reference_ids, response_shape,
                                     planning_images, validate_result)
from image_workflow.planning.request import build_planning_request as _build_planning_request
from image_workflow.planning.service import PlanningIO, execute_planning
from image_workflow.tasks.rules import context_version, stale_ids, plan_status, materialize_confirmations
from image_workflow.tasks.storage import TaskFiles
from image_workflow.tasks.images import TaskImageApplication
from api import register_routes
from image_workflow.tasks.service import TaskApplication, create_task, save_task
from image_workflow.tasks.queries import (TaskQueries, case_identifier, version as task_version,
                                         image_state as task_image_state, image_history as task_image_history,
                                         card_view as task_card_view)

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


class Store(TaskFiles):
    """Legacy Store surface; rules/use cases/queries live in the Task package."""

    def __init__(self, root, case_dir=None):
        super().__init__(root, case_dir, reader=lambda path: read_json(path),
                         writer=lambda path, value, exclusive=False: write_json(path, value, exclusive=exclusive))
        self.lock = threading.Lock()
        self.planning = {}

    def case_id(self, state):
        return case_identifier(self, state, historical_case_match)

    def save(self, state, event):
        return save_task(self, state, event, clock=now)

    def create(self, text, uploads, title, case_id=None, mode="product_pack", output_size="1024x1536", *,
               quick_business_version=None, quick_slots=None, image_sizes=None,
               quick_scenario=None, listing_slots=None, generation_quality=None, image_qualities=None):
        return create_task(self, text, uploads, title, case_id, mode, output_size, clock=now, new_id=uuid4,
                           contains_private=contains_private, sizes=SIZES, default_requirements=DEFAULT_REQUIREMENTS,
                           quick_business_version=quick_business_version, quick_slots=quick_slots, image_sizes=image_sizes,
                           quick_scenario=quick_scenario, listing_slots=listing_slots,
                           generation_quality=generation_quality, image_qualities=image_qualities)

    def version(self, state, revision):
        return task_version(self, state, revision)

    def image_state(self, state, target, required=True):
        return task_image_state(self, state, target, required)

    def image_history(self, state, target):
        return task_image_history(self, state, target)

    def card_view(self, generation, state, target):
        return task_card_view(self, generation.card, state, target)


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
    app = Flask("prepare_plan", root_path=str(Path(__file__).resolve().parent))
    app.config["MAX_CONTENT_LENGTH"] = 80 * 1024 * 1024
    app.config["MAX_FORM_MEMORY_SIZE"] = 2 * 1024 * 1024
    case = Path(case_dir or ROOT / ".runtime/inputs/case-001")
    store = Store(runtime_dir or ROOT / ".runtime/prepare-plan", case)
    generation = GenerationService(store)
    app.extensions["plan_store"] = store
    app.extensions["generation_service"] = generation
    tasks = TaskApplication(store, generation, planner=lambda state, action, target, feedback: call_ai(store, state, action, target, feedback),
                            clock=lambda: now(), writer=lambda path, value, exclusive=False: write_json(path, value, exclusive=exclusive))
    queries = TaskQueries(store, generation, auxiliary_purposes=auxiliary.AUXILIARY_PURPOSES,
                          auxiliary_max_bytes=auxiliary.MAX_AUXILIARY_BYTES, quick_sizes=SIZES)
    app.extensions["task_application"] = tasks
    app.extensions["task_queries"] = queries

    images = TaskImageApplication(store, generation, queries, review=image_review,
                                  exporter=lambda owner, session_id: export_experiment(owner, session_id),
                                  safe_text=lambda text: safe_text(text))
    app.extensions["task_image_application"] = images
    register_routes(app, store=store, generation=generation, tasks=tasks, queries=queries,
                    images=images, case=case, safe_text=lambda text: safe_text(text), auxiliary_uploads=auxiliary)

    return app


def create_local_debug_app(runtime_dir, allowed_task_ids=(), case_dir=None, *,
                           execution_mode='UNVERIFIED', allow_paid_actions=False,
                           allow_runtime_tasks=False, read_only_workspace=False):
    """Opt-in local composition; the pilot factory/signature remains unchanged."""
    if not runtime_dir:
        raise ValueError('调试侧栏必须显式指定独立 Runtime。')
    runtime = Path(runtime_dir).absolute()
    production = (ROOT / '.runtime/prepare-plan').absolute()
    if runtime == production or production in runtime.parents:
        raise ValueError('调试侧栏不能使用默认运营 Runtime，请提供隔离副本。')
    runtime = runtime.resolve()
    if runtime == production or production in runtime.parents:
        raise ValueError('调试侧栏不能通过路径别名使用默认运营 Runtime。')
    from api.inspector import register_inspector_routes
    app = create_app(runtime, case_dir or runtime / 'case-inputs')
    register_inspector_routes(app, runtime, allowed_task_ids, integrated=True,
                              execution_mode=execution_mode, allow_paid_actions=allow_paid_actions,
                              allow_runtime_tasks=allow_runtime_tasks, read_only_workspace=read_only_workspace)
    return app


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8010)
    args = parser.parse_args()
    create_app().run(host="127.0.0.1", port=args.port, debug=False)
