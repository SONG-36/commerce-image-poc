"""Legacy Review and auxiliary-input compatibility bindings; no business policy."""

from datetime import datetime, timezone
import io
from pathlib import Path
from uuid import uuid4

from file_ops import read_json, safe_path, sha256, write_json_atomic
import evidence as _evidence
from evidence import contains_private
from PIL import Image
from persistence.review_state import ReviewFiles
from image_workflow.review import (ImageScope, ReviewIO, apply_review, export_passed as export_accepted,
                                   image_bytes as reviewed_image_bytes, versions as review_versions)
from image_workflow.tasks import review as _task_review
from image_workflow.generation import auxiliary as _auxiliary


MAX_AUXILIARY_BYTES = _auxiliary.MAX_AUXILIARY_BYTES
AUXILIARY_PURPOSES = _auxiliary.AUXILIARY_PURPOSES


def prepare_auxiliary(name, data, purpose):
    """Compatibility bindings only; Generation owns the input policy."""
    return _auxiliary.prepare_auxiliary(
        name, data, purpose, purposes=AUXILIARY_PURPOSES, max_bytes=MAX_AUXILIARY_BYTES,
        private=contains_private, sanitize=lambda text: _evidence.safe_text(text),
        image_type=Image, hash_bytes=sha256)


def auxiliary_prompt(reference, slot):
    return _auxiliary.auxiliary_prompt(reference, slot)


def _scope(state, target):
    return _task_review.image_scope(state, target, scope_type=ImageScope)


def _files(service, state, target):
    return _task_review.review_files(service, state, target, reader=read_json,
                                     writer=write_json_atomic, files_type=ReviewFiles)


def _io(service, state):
    from evidence import clean_record
    return _task_review.review_io(
        service, state, new_id=uuid4, utc_now=lambda: datetime.now(timezone.utc),
        sanitize=clean_record, private=contains_private, io_type=ReviewIO)


def versions(service, state, target):
    return _task_review.versions(service, state, target, scope_for=_scope,
                                 files_for=_files, version_reader=review_versions)


def image_bytes(service, state, target, run_id):
    return _task_review.image_bytes(service, state, target, run_id, scope_for=_scope,
                                    files_for=_files, image_reader=reviewed_image_bytes)


def review(service, state, target, kind, run_id, expected_revision):
    return _task_review.review(service, state, target, kind, run_id, expected_revision,
                               scope_for=_scope, files_for=_files, io_for=_io, apply=apply_review)


def export_passed(service, state):
    return _task_review.export_passed(service, state, files_for=_files,
                                      io_for=_io, exporter=export_accepted)
