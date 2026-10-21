"""Read-only version identities/metadata, separate from generation execution."""

from persistence.review_state import ReviewFiles
from .validation import ImageScope, validate_image_bytes, validate_run_scope


def versions(scope: ImageScope, files: ReviewFiles):
    result = []
    for run_id, record in files.run_records():
        if record.get('status') != 'SUCCEEDED':
            continue
        validate_run_scope(record, run_id, scope)
        files.run_folder(run_id)
        result.append({'run_id': run_id, 'created_at': record.get('image_created_at', record.get('finished_at', record['started_at'])),
                       'version': record.get('version'),
                       'action': record.get('action', 'generate_image'), 'feedback': record.get('feedback', ''),
                       'parent_run_id': record.get('parent_run_id'), 'confirmed_revision': scope.revision})
        if record.get('auxiliary_reference'):
            result[-1]['auxiliary_reference'] = record['auxiliary_reference']
    result.sort(key=lambda row: (row['created_at'], row['run_id']))
    legacy = [row for row in result if row['version'] is None]
    for index, row in enumerate(legacy, 1):
        row['version'] = index
    result.sort(key=lambda row: row['version'])
    for row in result:
        row['url'] = f"/api/sessions/{scope.task_id}/generated-images/{scope.revision}/{scope.image_id}/{row['run_id']}"
    return result


def image_bytes(scope: ImageScope, files: ReviewFiles, run_id):
    version = next((v for v in versions(scope, files) if v['run_id'] == run_id), None)
    if not version:
        raise ValueError('所选图片版本不属于本任务、本张图片或当前确认计划。')
    record, data = files.read_image(run_id)
    validate_image_bytes(record, data)
    return data, version
