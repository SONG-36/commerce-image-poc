"""Task-scoped Review adaptation using the existing image coordinator lock."""

from datetime import datetime, timezone
from uuid import uuid4

from file_ops import read_json, write_json_atomic
from infrastructure.evidence import clean_record, contains_private
from persistence.review_state import ReviewFiles
from image_workflow.review import (ImageScope, ReviewIO, apply_review, export_passed as export_accepted,
                                   image_bytes as reviewed_image_bytes, versions as review_versions)


def image_scope(state, target):
    return ImageScope(state['id'], state['revision'], target)


def review_files(service, state, target):
    return ReviewFiles(
        card_folder=lambda: service.folder(state['id'], state['revision'], target),
        run_folder=lambda run_id: service.run_folder(state['id'], state['revision'], target, run_id),
        pointer_reader=read_json, pointer_writer=write_json_atomic)


def review_io(service, state):
    return ReviewIO(new_id=uuid4, utc_now=lambda: datetime.now(timezone.utc),
                    case_id=lambda: service.store.case_id(state), sanitize=clean_record,
                    contains_private=contains_private)


def versions(service, state, target):
    return review_versions(image_scope(state, target), review_files(service, state, target))


def image_bytes(service, state, target, run_id):
    return reviewed_image_bytes(image_scope(state, target), review_files(service, state, target), run_id)


def review(service, state, target, kind, run_id, expected_revision, **feedback):
    with service.review_operation(state, target):
        return apply_review(image_scope(state, target), review_files(service, state, target), kind, run_id,
                            expected_revision, io=review_io(service, state), **feedback)


def export_passed(service, state):
    return export_accepted(state, targets=lambda: service.targets(state),
                           image_history=lambda target: service.store.image_history(state, target),
                           files_for=lambda saved, target: review_files(service, saved, target), io=review_io(service, state))
