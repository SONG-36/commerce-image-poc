"""Read-only per-Run/card projections; borrow coordination state, never own it."""

import re

from file_ops import safe_path
import image_workflow.generation.quick_v1 as quick_v1
from image_workflow.generation.request import parameters_for


def request_uncertain(record, status=None):
    status = status or record.get('status')
    code = (record.get('error') or {}).get('status_code')
    return bool(status in ['RUNNING', 'INTERRUPTED'] or status == 'FAILED' and record.get('api_call_attempted', False)
                and not (isinstance(code, int) and 400 <= code < 500 and code != 408))


def generation_card(service, state, target, *, reader, safe_text, defaults, review, uncertainty):
    revision = state["revision"]
    folder = service.folder(state["id"], revision, target)
    pointer = reader(folder / "current.json") if (folder / "current.json").is_file() else {}
    latest = pointer.get("latest_run")
    record = reader(service.run_folder(state["id"], revision, target, latest) / "run.json") if latest else {}
    status = record.get("status", "NOT_STARTED")
    key = (state["id"], revision, target)
    with service.guard:
        active = key in service.active
    if status == "RUNNING" and not active:
        status = "INTERRUPTED"
    history = review.versions(service, state, target)
    successful = pointer.get("selected_run", pointer.get("last_successful_run"))
    image_url = None
    if successful:
        saved = service.run_folder(state["id"], revision, target, successful)
        if reader(saved / "run.json").get("status") == "SUCCEEDED" and (saved / "image.png").is_file():
            image_url = f"/api/sessions/{state['id']}/generated-images/{revision}/{target}/{successful}"
    slot = quick_v1.output_slot(state, target) if quick_v1.is_v1(state) else None
    reference_id = slot['reference_id'] if slot else target
    reference = next(image for image in state["images"] if image["id"] == reference_id)
    error = record.get("error")
    return {
        "id": target, "plan": state["plans"].get(target), "confirmed_revision": revision,
        "requirements": state["inputs"]["requirements"], "product_facts": state["inputs"].get("product_facts", ""),
        "output_size": parameters_for(state, defaults, target)['size'],
        "style_references": [{"name": image["name"], "url": f"/api/sessions/{state['id']}/images/{image['id']}"}
                             for image in state["images"] if state.get("mode") == "quick_redesign" and not slot and image["role"] == "reference"],
        "reference": {"name": reference["name"], "url": f"/api/sessions/{state['id']}/images/{reference_id}"},
        **({'output_slot': slot, 'quick_business_version': quick_v1.VERSION} if slot else {}),
        "status": status, "run_id": latest, "image_url": image_url,
        "image_is_latest": bool(successful and successful == latest),
        "error": safe_text(error.get("message", "")) if error else None,
        "versions": history, "selected_run": successful, "passed_run": pointer.get("passed_run"),
        "card_revision": pointer.get("card_revision", 0), "started_at": record.get("api_started_at", record.get("started_at")),
        "operation": record.get("action", "generate_image"),
        "api_call_attempted": record.get('api_call_attempted', False),
        "request_uncertain": uncertainty(record, status),
    }


def generation_operation(service, state, target, operation_id, *, reader, safe_text, uncertainty, path_check=safe_path):
    """Only query a specific submitted request. A missing record never authorizes a retry."""
    if not re.fullmatch(r'[0-9a-f]{32}', operation_id):
        raise ValueError('无效的操作标识。')
    folder = service.folder(state['id'], state['revision'], target)
    for path in (folder / 'runs').glob('*/run.json'):
        record = reader(path_check(folder, str(path.relative_to(folder))))
        if record.get('operation_id') != operation_id:
            continue
        if record.get('session_id') != state['id'] or record.get('reference_id') != target or record.get('confirmed_revision') != state['revision']:
            raise ValueError('操作记录与本任务不一致。')
        status = record['status']
        with service.guard:
            active = (state['id'], state['revision'], target) in service.active
        if status == 'RUNNING' and not active:
            status = 'INTERRUPTED'
        error = record.get('error') or {}
        return {'operation_id': operation_id, 'run_id': record['run_id'], 'status': status,
                'api_call_attempted': record.get('api_call_attempted', False), 'uncertain': uncertainty(record, status),
                'error': safe_text(error.get('message', '')), 'confirmed_revision': state['revision']}
    return {'operation_id': operation_id, 'status': 'NOT_FOUND', 'uncertain': True}
