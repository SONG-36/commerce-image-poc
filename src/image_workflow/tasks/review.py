"""Task-scoped Review adaptation; reuse the coordinator's existing image lock.

Review owns version/Pass rules, ReviewFiles owns file access. This module only
builds their scope/adapters and coordinates calls; it owns no locks or state.
Keyword adapters retain the legacy facade's late-bound override seams.
"""

from datetime import datetime, timezone
from uuid import uuid4

from file_ops import read_json, write_json_atomic
from infrastructure.evidence import clean_record, contains_private
from persistence.review_state import ReviewFiles
from image_workflow.review import (ImageScope, ReviewIO, apply_review, export_passed as export_accepted,
                                   image_bytes as reviewed_image_bytes, versions as review_versions)


def image_scope(state, target, *, scope_type=ImageScope):
    return scope_type(state['id'], state['revision'], target)


def review_files(service, state, target, *, reader=read_json, writer=write_json_atomic, files_type=ReviewFiles):
    return files_type(
        card_folder=lambda: service.folder(state['id'], state['revision'], target),
        run_folder=lambda run_id: service.run_folder(state['id'], state['revision'], target, run_id),
        pointer_reader=reader, pointer_writer=writer)


def review_io(service, state, *, new_id=uuid4, utc_now=lambda: datetime.now(timezone.utc),
              sanitize=clean_record, private=contains_private, io_type=ReviewIO):
    return io_type(new_id=new_id, utc_now=utc_now,
                   case_id=lambda: service.store.case_id(state), sanitize=sanitize,
                   contains_private=private)


def versions(service, state, target, *, scope_for=image_scope, files_for=review_files, version_reader=review_versions):
    return version_reader(scope_for(state, target), files_for(service, state, target))


def image_bytes(service, state, target, run_id, *, scope_for=image_scope, files_for=review_files,
                image_reader=reviewed_image_bytes):
    return image_reader(scope_for(state, target), files_for(service, state, target), run_id)


def review(service, state, target, kind, run_id, expected_revision, *, scope_for=image_scope,
           files_for=review_files, io_for=review_io, apply=apply_review):
    with service.review_operation(state, target):
        return apply(scope_for(state, target), files_for(service, state, target), kind, run_id,
                     expected_revision, io=io_for(service, state))


def export_passed(service, state, *, files_for=review_files, io_for=review_io, exporter=export_accepted):
    return exporter(state, targets=lambda: service.targets(state),
                    image_history=lambda target: service.store.image_history(state, target),
                    files_for=lambda saved, target: files_for(service, saved, target), io=io_for(service, state))
