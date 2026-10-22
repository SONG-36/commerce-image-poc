"""Legacy Generation imports and late-bound execution assembly for Task coordination."""

from contextlib import contextmanager
from datetime import datetime, timezone
from importlib.metadata import version
import os
from pathlib import Path
import re
import threading
import time
from uuid import uuid4

from infrastructure.openai_images import MODELS, PARAMETERS, TIMEOUT_SECONDS, make_client
from evidence import clean_record, safe_text
from file_ops import read_json as read_json_file, safe_path, sha256, write_json_atomic
import image_review
from image_workflow.generation import quick_prompt
from image_workflow.generation import GenerationIO, RunAccess, build_edit_prompt, build_prompt, execute_generation
from image_workflow.generation.request import PromptBuilders
from image_workflow.tasks.generation import GenerationService as _TaskGenerationService, GenerationRuntime
from image_workflow.tasks.generation_queries import request_uncertain as _request_uncertain


def now():
    return datetime.now(timezone.utc).isoformat()


def write_json(path, value):
    write_json_atomic(path, value, transform=clean_record)


def read_json(path):
    return read_json_file(path)


def request_uncertain(record, status=None):
    return _request_uncertain(record, status)


def _runtime():
    io = GenerationIO(
        client_factory=make_client, write_json=write_json, read_json=read_json, safe_text=safe_text,
        now=now, new_run_id=lambda: datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex,
        sdk_version=version, source_file=Path(__file__),
        t01_source_file=Path(__file__).with_name("generate_image.py"),
        quick_source_file=Path(__file__).with_name("quick_redesign.py"), clock=time.perf_counter)
    prompts = PromptBuilders(build_prompt, build_edit_prompt, quick_prompt.build_prompt,
                             quick_prompt.build_edit_prompt, image_review.auxiliary_prompt)
    return GenerationRuntime(
        io=io, prompts=prompts, executor=execute_generation, environment=os.environ,
        models=MODELS, defaults=PARAMETERS, quick_sizes=quick_prompt.SIZES,
        timeout_seconds=TIMEOUT_SECONDS)


class GenerationService(_TaskGenerationService):
    """Original constructor/import path; Task owns coordination and state."""

    def __init__(self, store):
        super().__init__(
            store, runtime=_runtime, review=image_review,
            prepare_auxiliary=lambda name, data, purpose: image_review.prepare_auxiliary(name, data, purpose),
            uncertainty=lambda record, status=None: request_uncertain(record, status),
            path_checker=lambda root, relative: safe_path(root, relative))
