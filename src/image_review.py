"""Per-card review and image history, using the existing generation Run folders."""

from datetime import datetime, timezone
import io
import json
import threading
from uuid import uuid4
import zipfile

from experiment_export import safe_path
from evidence import contains_private
from generate_image import sha256


def versions(service, state, target):
    folder = service.folder(state['id'], state['revision'], target)
    runs = safe_path(folder, 'runs')
    result = []
    if runs.is_dir():
        for child in sorted(runs.iterdir()):
            path = safe_path(folder, 'runs/' + child.name + '/run.json')
            if not path.is_file():
                continue
            record = json.loads(path.read_text())
            if record.get('status') != 'SUCCEEDED':
                continue
            # Scope every version to this task, confirmed plan and reference.
            if record.get('run_id') != child.name or record.get('session_id') != state['id'] or record.get('reference_id') != target or record.get('confirmed_revision') != state['revision']:
                raise ValueError('图片记录与当前任务不一致，已停止操作。')
            service.run_folder(state['id'], state['revision'], target, child.name)
            result.append({'run_id': child.name, 'created_at': record.get('image_created_at', record.get('finished_at', record['started_at'])),
                           'version': record.get('version'),
                           'action': record.get('action', 'generate_image'), 'feedback': record.get('feedback', ''),
                           'parent_run_id': record.get('parent_run_id'), 'confirmed_revision': state['revision']})
    result.sort(key=lambda row: (row['created_at'], row['run_id']))
    legacy = [row for row in result if row['version'] is None]
    for index, row in enumerate(legacy, 1):
        row['version'] = index
    result.sort(key=lambda row: row['version'])
    for row in result:
        row['url'] = f"/api/sessions/{state['id']}/generated-images/{state['revision']}/{target}/{row['run_id']}"
    return result


def image_bytes(service, state, target, run_id):
    version = next((v for v in versions(service, state, target) if v['run_id'] == run_id), None)
    if not version:
        raise ValueError('所选图片版本不属于本任务、本张图片或当前确认计划。')
    folder = service.run_folder(state['id'], state['revision'], target, run_id)
    record = json.loads(safe_path(folder, 'run.json').read_text())
    data = safe_path(folder, 'image.png').read_bytes()
    if not record.get('output', {}).get('validated') or sha256(data) != record['output']['sha256']:
        raise ValueError('图片文件与保存的记录不一致，已停止操作。')
    return data, version


def review(service, state, target, kind, run_id, expected_revision):
    key = (state['id'], state['revision'], target)
    with service.guard:
        lock = service.locks.setdefault(key, threading.Lock())
    if not lock.acquire(blocking=False):
        raise ValueError('本张图片正在处理，请完成后再选择或审核。')
    with service.guard:
        service.active.add(key)
    try:
        from generate_plan_image import read_json, write_json
        folder = service.folder(*key)
        pointer = read_json(folder / 'current.json') if (folder / 'current.json').is_file() else {}
        if expected_revision != pointer.get('card_revision', 0):
            raise ValueError('图片状态已改变，请刷新后再操作。')
        if kind not in ('select', 'pass'):
            raise ValueError('不支持的图片审核操作。')
        _, selected = image_bytes(service, state, target, run_id)
        if kind == 'pass' and run_id != pointer.get('selected_run', pointer.get('last_successful_run')):
            raise ValueError('请先选择要审核的图片版本。')
        event = {'id': uuid4().hex, 'task_id': state['id'], 'case_id': service.store.case_id(state),
                 'reference_id': target, 'confirmed_revision': state['revision'], 'action': kind,
                 'created_at': datetime.now(timezone.utc).isoformat(), 'version': selected['version'], 'run_id': run_id,
                 'before_selected_run': pointer.get('selected_run', pointer.get('last_successful_run')),
                 'before_passed_run': pointer.get('passed_run'), 'card_revision': expected_revision + 1}
        pointer['selected_run'] = run_id
        if kind == 'pass':
            pointer['passed_run'] = run_id
            pointer['passed_at'] = event['created_at']
        pointer['card_revision'] = expected_revision + 1
        event['after_passed_run'] = pointer.get('passed_run')
        events = safe_path(folder, 'reviews')
        events.mkdir(exist_ok=True)
        with (events / (event['id'] + '.json')).open('x', encoding='utf-8') as stream:
            from evidence import clean_record
            stream.write(json.dumps(clean_record(event), ensure_ascii=False, indent=2) + '\n')
        write_json(folder / 'current.json', pointer)
        return event
    finally:
        with service.guard:
            service.active.discard(key)
        lock.release()


def export_passed(service, state):
    """Only the explicitly accepted version; selection alone never changes acceptance."""
    from generate_plan_image import read_json
    output = io.BytesIO()
    count = 0
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        for index, target in enumerate(state['plans'], 1):
            path = safe_path(service.folder(state['id'], state['revision'], target), 'current.json')
            pointer = read_json(path) if path.is_file() else {}
            if pointer.get('passed_run'):
                data, version = image_bytes(service, state, target, pointer['passed_run'])
                if contains_private(data.decode('utf-8', errors='ignore')):
                    raise ValueError('图片包含认证信息，已停止导出。')
                archive.writestr(f"图片_{index:02}_V{version['version']}.png", data)
                count += 1
    if not count:
        raise ValueError('当前任务尚无已 Pass 的图片，请先人工审核。')
    output.seek(0)
    return output, 'task-' + state['id'] + '-passed-' + datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f') + '.zip'
