"""Register the existing Flask API without changing URL or endpoint identities.

Only HTTP parsing, representation and error rendering live here. Task and image
use cases are provided by the composition root; this module never imports it.
"""

import io
import os

from flask import jsonify, render_template, request, send_file, redirect
from werkzeug.exceptions import HTTPException

from file_ops import ExportError
from image_workflow import Problem


def register_routes(app, *, store, generation, tasks, queries, images, case, safe_text, auxiliary_uploads):

    @app.before_request
    def local_action():
        if request.method == "POST":
            if request.headers.get("Origin") and request.headers["Origin"] != request.host_url.rstrip("/"):
                raise Problem("仅接受当前页面提交的操作。", 403)
            if request.headers.get("X-Local-Action") != "prepare-plan":
                raise Problem("请从准备与规划页面执行操作。", 403)

    @app.errorhandler(Problem)
    def problem(error):
        return jsonify(error=safe_text(str(error))), error.status

    @app.errorhandler(HTTPException)
    def http_problem(error):
        return jsonify(error="上传体积过大，请减少图片或文件大小。" if error.code == 413 else error.description), error.code

    @app.errorhandler(ExportError)
    def unsafe_path(error):
        return jsonify(error=safe_text(str(error))), 409

    activity = queries.activity

    public = queries.public

    @app.get("/")
    def home():
        legacy = request.args.get('session')
        if legacy:
            store.load(legacy)
            return redirect('/prepare/' + legacy)
        return render_template('tasks.html')

    @app.get('/workspace/new')
    @app.get('/prepare/new')
    def new_task_page():
        return render_template('prepare.html', session_id='')

    @app.get('/workspace/<session_id>')
    @app.get('/prepare/<session_id>')
    def prepare_page(session_id):
        store.load(session_id)
        return render_template('prepare.html', session_id=session_id)

    @app.get('/api/tasks')
    def task_list():
        return jsonify(tasks=queries.task_list())

    confirmed_state = queries.confirmed_state

    generation_view = queries.generation_view

    @app.get("/generate/<session_id>")
    def generate_page(session_id):
        store.load(session_id)
        return render_template("generate.html", session_id=session_id)

    @app.get('/api/sessions/<session_id>/workspace')
    def workspace_state(session_id):
        return jsonify(**queries.workspace(session_id), ai_configured=bool(os.environ.get('OPENAI_API_KEY', '')))

    @app.post("/api/sessions/<session_id>/export-experiment")
    def export_case(session_id):
        package, filename = images.export_case(session_id)
        return send_file(package, mimetype="application/zip", as_attachment=True, download_name=filename, max_age=0)

    @app.get("/api/sessions/<session_id>/generation")
    def generation_state(session_id):
        state = confirmed_state(session_id)
        return jsonify(generation_view(state))

    @app.post('/api/sessions/<session_id>/review/<target>')
    def review_one(session_id, target):
        return jsonify(event=images.review_one(session_id, target, request.get_json))

    @app.post('/api/sessions/<session_id>/revise/<target>')
    def revise_one(session_id, target):
        state = images.edit_state(session_id, target)
        multipart = request.mimetype == 'multipart/form-data'
        body = request.form.to_dict() if multipart else request.get_json()
        if multipart:
            try:
                for key in ('confirmed_revision', 'card_revision'):
                    body[key] = int(body[key])
            except (KeyError, ValueError) as error:
                raise Problem('图片版本信息无效，请刷新后重新修改。') from error
        elif isinstance(body, dict) and any(key in body for key in ('auxiliary', 'auxiliary_reference', 'auxiliary_path', 'auxiliary_purpose')):
            raise Problem('辅助图片必须随本次修改上传实际文件，不能使用路径或其他任务的图片标识。')
        def read_auxiliary():
            auxiliary = None
            if multipart:
                uploads = [(name, file) for name in request.files for file in request.files.getlist(name)]
                if len(uploads) > 1 or any(name != 'auxiliary' for name, _ in uploads):
                    raise Problem('每次修改最多新增一张辅助参考图片。')
                if uploads:
                    file = uploads[0][1]
                    try:
                        auxiliary = auxiliary_uploads.prepare_auxiliary(file.filename, file.read(auxiliary_uploads.MAX_AUXILIARY_BYTES + 1), body.get('auxiliary_purpose'))
                    except ValueError as error:
                        raise Problem(str(error)) from error
                elif body.get('auxiliary_purpose'):
                    raise Problem('请选择本次辅助图片，或清除辅助图片用途后仅用文字修改。')
            return auxiliary
        return generation_result(images.revise(state, target, body, read_auxiliary))

    @app.post('/api/sessions/<session_id>/export-passed')
    def passed_images(session_id):
        package, filename = images.passed_images(session_id)
        return send_file(package, mimetype='application/zip', as_attachment=True, download_name=filename, max_age=0)

    def generation_result(record):
        if record['status'] == 'FAILED':
            message = safe_text(record['error']['message'])
            if record['api_call_attempted']:
                message += '；服务端是否执行或计费尚未确认，未自动重试，已保留之前成功的图片。'
            return jsonify(error=message, run_id=record['run_id'], confirmed_revision=record['confirmed_revision']), 502 if record['api_call_attempted'] else 400
        return jsonify(run_id=record['run_id'], confirmed_revision=record['confirmed_revision'], status='SUCCEEDED')

    @app.post("/api/sessions/<session_id>/generate/<target>")
    def generate_one(session_id, target):
        return generation_result(images.generate_one(session_id, target, request.get_json))

    @app.get('/api/sessions/<session_id>/operations/<target>/<operation_id>')
    def operation_status(session_id, target, operation_id):
        return jsonify(images.operation_status(session_id, target, operation_id,
                                               lambda: request.args.get('confirmed_revision', '')))

    @app.get("/api/sessions/<session_id>/generated-images/<int:revision>/<target>/<run_id>")
    def generated_image(session_id, revision, target, run_id):
        return send_file(io.BytesIO(images.generated_image(session_id, revision, target, run_id)), mimetype="image/png")

    @app.get("/api/current")
    def current():
        state = store.load_current()
        return jsonify(state=public(state) if state else None, activity=activity(state) if state else None,
                       ai_configured=bool(os.environ.get("OPENAI_API_KEY", "")))

    @app.get("/api/sessions/<session_id>")
    def saved_session(session_id):
        state = store.load(session_id)
        return jsonify(state=public(state), activity=activity(state), ai_configured=bool(os.environ.get("OPENAI_API_KEY", "")))

    @app.get("/api/sessions/<session_id>/images/<image_id>")
    def image_file(session_id, image_id):
        path, mime = queries.image_file(session_id, image_id)
        return send_file(path, mimetype=mime)

    @app.post("/api/case-001")
    def load_case():
        return jsonify(state=public(tasks.load_case(case)))

    @app.post("/api/sessions")
    def save_inputs():
        def read_uploads():
            return [(role, file.filename, file.read()) for role in ["product", "reference"]
                    for file in request.files.getlist(role) if file.filename]
        return jsonify(state=public(tasks.save_inputs(lambda: request.form, read_uploads)))

    @app.post("/api/sessions/<session_id>/action")
    def action(session_id):
        return jsonify(state=public(tasks.action(session_id, request.get_json)))
