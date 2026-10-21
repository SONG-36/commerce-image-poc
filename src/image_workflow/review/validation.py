"""Existing ownership, conflict and integrity checks, never visual evaluation."""

from dataclasses import dataclass

from file_ops import sha256


@dataclass(frozen=True)
class ImageScope:
    task_id: str
    revision: int
    image_id: str


def validate_run_scope(record, run_id, scope: ImageScope):
    if (record.get('run_id') != run_id or record.get('session_id') != scope.task_id
            or record.get('reference_id') != scope.image_id or record.get('confirmed_revision') != scope.revision):
        raise ValueError('图片记录与当前任务不一致，已停止操作。')


def validate_review_request(pointer, kind, expected_revision):
    # Order matters: stale revision takes precedence over an unknown action.
    if expected_revision != pointer.get('card_revision', 0):
        raise ValueError('图片状态已改变，请刷新后再操作。')
    if kind not in ('select', 'pass'):
        raise ValueError('不支持的图片审核操作。')


def validate_pass_selection(pointer, kind, run_id):
    if kind == 'pass' and run_id != pointer.get('selected_run', pointer.get('last_successful_run')):
        raise ValueError('请先选择要审核的图片版本。')


def validate_image_bytes(record, data):
    # This verifies saved technical validity and hash, not subjective quality.
    if not record.get('output', {}).get('validated') or sha256(data) != record['output']['sha256']:
        raise ValueError('图片文件与保存的记录不一致，已停止操作。')
