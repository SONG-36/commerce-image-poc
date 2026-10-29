"""Human selection/Pass and final delivery, without AI or execution state.

The application boundary holds the SAME image lock used by Generation. This
package receives scoped file access, never its locks/active set or a Web service.
"""

from dataclasses import dataclass
import io as byte_stream
from typing import Callable
import zipfile

from persistence.review_state import ReviewFiles
from .validation import ImageScope, validate_pass_selection, validate_review_request, REJECT_REASONS
from .versioning import image_bytes


@dataclass(frozen=True)
class ReviewIO:
    new_id: Callable
    utc_now: Callable
    case_id: Callable
    sanitize: Callable
    contains_private: Callable


def review_transition(scope, pointer, selected, kind, run_id, expected_revision, *, event_id, case_id, created_at):
    """Pure event/pointer construction after the caller's ordered checks.

    Selection changes only selected_run; explicit Pass additionally changes
    passed_run/passed_at. No generation, task revision or implicit acceptance.
    """
    event = {'id': event_id, 'task_id': scope.task_id, 'case_id': case_id,
             'reference_id': scope.image_id, 'confirmed_revision': scope.revision, 'action': kind,
             'created_at': created_at, 'version': selected['version'], 'run_id': run_id,
             'before_selected_run': pointer.get('selected_run', pointer.get('last_successful_run')),
             'before_passed_run': pointer.get('passed_run'), 'card_revision': expected_revision + 1}
    pointer = dict(pointer)
    pointer['selected_run'] = run_id
    if kind == 'pass':
        pointer['passed_run'] = run_id
        pointer['passed_at'] = event['created_at']
    pointer['card_revision'] = expected_revision + 1
    event['after_passed_run'] = pointer.get('passed_run')
    return event, pointer


def apply_review(scope: ImageScope, files: ReviewFiles, kind, run_id, expected_revision, *, io: ReviewIO,
                 reason=None, note=''):
    """Validate, build and persist one explicit human action; caller owns lock."""
    folder = files.card_folder()
    pointer = files.read_pointer(folder)
    validate_review_request(pointer, kind, expected_revision)
    if kind == 'reject' and (reason not in REJECT_REASONS or not isinstance(note, str) or len(note) > 12000
                             or io.contains_private(note)):
        raise ValueError('请选择有效拒绝原因；说明最多 12000 字，不包含认证信息。')
    _, selected = image_bytes(scope, files, run_id)
    validate_pass_selection(pointer, kind, run_id)
    event_id = io.new_id().hex
    case_id = io.case_id()
    created_at = io.utc_now().isoformat()
    event, pointer = review_transition(scope, pointer, selected, kind, run_id, expected_revision,
                                       event_id=event_id, case_id=case_id, created_at=created_at)
    if kind == 'reject':
        event.update(reason=reason, note=note, source='HUMAN_REVIEW')
    files.save_review(folder, event, pointer, sanitize=io.sanitize)
    return event


def accepted_images(*, targets, image_history, files_for):
    """Yield only the first explicitly accepted bucket per image, in task order.

    Snapshot iteration/ownership remains with Store; selection does not fall
    back after a corrupt accepted version and never substitutes an unpassed one.
    """
    for index, target in enumerate(targets(), 1):
        accepted = None
        for saved in image_history(target):
            files = files_for(saved, target)
            pointer = files.read_pointer(files.card_folder(), checked=True)
            if pointer.get('passed_run'):
                accepted = (saved, pointer['passed_run'])
                break
        if accepted:
            saved, run_id = accepted
            scope = ImageScope(saved['id'], saved['revision'], target)
            data, version = image_bytes(scope, files_for(saved, target), run_id)
            yield index, data, version


def export_passed(state, *, targets, image_history, files_for, io: ReviewIO):
    """Final image ZIP only, distinct from experimental Evidence export."""
    output = byte_stream.BytesIO()
    count = 0
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        for index, data, version in accepted_images(targets=targets, image_history=image_history, files_for=files_for):
            if io.contains_private(data.decode('utf-8', errors='ignore')):
                raise ValueError('图片包含认证信息，已停止导出。')
            archive.writestr(f"图片_{index:02}_V{version['version']}.png", data)
            count += 1
    if not count:
        raise ValueError('当前任务尚无已 Pass 的图片，请先人工审核。')
    output.seek(0)
    return output, 'task-' + state['id'] + '-passed-' + io.utc_now().strftime('%Y%m%d-%H%M%S-%f') + '.zip'
