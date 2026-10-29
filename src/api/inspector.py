"""Explicit, loopback-only Inspector process; never registered on the pilot app.

Run with PYTHONPATH=src python -B -m api.inspector --runtime-dir ... --task-id ...
"""

import argparse
from ipaddress import ip_address
import io
import os
from pathlib import Path
from urllib.parse import urlsplit

from flask import Flask, abort, jsonify, render_template, request, send_file

from image_workflow.inspector import InspectorReader


def register_inspector_routes(app, runtime_dir, allowed_task_ids, *, integrated=False,
                              execution_mode='UNVERIFIED', allow_paid_actions=False,
                              allow_runtime_tasks=False, read_only_workspace=False):
    """Reuse V0 on an explicitly isolated local app; never enable via environment."""
    if type(allow_runtime_tasks) is not bool or (allow_runtime_tasks and
            (not integrated or execution_mode != 'LIVE DEBUG')):
        raise ValueError('Runtime 任务范围仅适用于隔离的本地 LIVE DEBUG 应用。')
    reader = InspectorReader(runtime_dir, allowed_task_ids, allow_runtime_tasks=allow_runtime_tasks)
    notices = {
        'MOCK': '离线模拟，不代表真实 GPT 调用；Usage / request_id 为测试记录。',
        'LIVE DEBUG': '正式 SDK 客户端；真实请求可能产生费用，不代表图片质量已通过。',
        'UNVERIFIED': '未标注执行环境，不能据此确认真实 GPT 调用。',
    }
    if execution_mode not in notices or type(allow_paid_actions) is not bool:
        raise ValueError('必须使用明确的服务端调试环境配置。')
    if type(read_only_workspace) is not bool or (read_only_workspace and
            (not integrated or execution_mode != 'MOCK' or allow_paid_actions or allow_runtime_tasks)):
        raise ValueError('匿名只读预览只适用于显式的 MOCK 白名单实例。')

    def debug_config(identity=None):
        return {'mode': execution_mode, 'notice': notices[execution_mode],
                'task_id': identity, 'authorized': reader.allows_task(identity),
                'task_scope': 'runtime' if allow_runtime_tasks else 'allowlist',
                'key_configured': bool(os.environ.get('OPENAI_API_KEY', '').strip()),
                'paid_actions_enabled': allow_paid_actions,
                'read_only_workspace': read_only_workspace,
                'busy': bool(integrated and (app.extensions['plan_store'].lock.locked() or
                                            app.extensions['generation_service'].active)),
                'pid': os.getpid(), 'runtime_dir': str(reader.root)}

    def inspector_request():
        return request.path == '/inspector' or request.path.startswith(('/api/inspector/', '/inspector-assets/'))

    @app.before_request
    def local_read_only():
        try:
            local = ip_address(request.remote_addr or '').is_loopback
            host = urlsplit('http://' + request.host).hostname
        except ValueError:
            abort(404)
        if not local or host not in ('localhost', '127.0.0.1', '::1'):
            abort(404)
        if any(header in request.headers for header in ('Forwarded', 'X-Forwarded-For', 'X-Real-IP', 'X-Forwarded-Host')):
            abort(404)
        if request.headers.get('Sec-Fetch-Site') == 'cross-site' or request.headers.get('Origin') not in (None, request.host_url.rstrip('/')):
            abort(404)
        if (read_only_workspace or not integrated or inspector_request()) and request.method not in ('GET', 'HEAD'):
            abort(405)
        if integrated and execution_mode == 'LIVE DEBUG' and request.method == 'POST':
            endpoint = request.endpoint
            body = request.get_json(silent=True) if endpoint == 'action' else None
            paid = endpoint in ('generate_one', 'revise_one') or (
                endpoint == 'action' and (not isinstance(body, dict) or body.get('action') not in ('confirm', 'resolve_conflict', 'manual_plan', 'set_quality')))
            if paid:
                identity = (request.view_args or {}).get('session_id')
                if not reader.allows_task(identity):
                    message = '当前 Task 不在本地 Debug Runtime 内或资料无效。' if allow_runtime_tasks else '当前 Task 未获调试授权。'
                    return jsonify(error=message, code='TASK_NOT_AUTHORIZED', api_call_attempted=False), 403
                if not allow_paid_actions or not debug_config()['key_configured']:
                    message = ('未配置 OpenAI API Key，请填写项目根目录 .env 后重新执行 ./scripts/start_live_debug.sh。'
                               if not debug_config()['key_configured'] else '模型操作未启用，请使用 ./scripts/start_live_debug.sh 启动。')
                    return jsonify(error=message,
                                   code='LIVE_CALLS_LOCKED', api_call_attempted=False), 403

    @app.after_request
    def private_response(response):
        if integrated and not inspector_request():
            return response
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        ancestors = "'self'" if integrated and request.path == '/inspector' and request.args.get('embedded') == '1' else "'none'"
        response.headers['Content-Security-Policy'] = f"default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; frame-ancestors {ancestors}; base-uri 'none'; form-action 'none'"
        return response

    def selection():
        try:
            revision = int(request.args['revision']) if 'revision' in request.args else None
        except ValueError:
            abort(404)
        return request.args.get('image_id'), revision, request.args.get('run_id')

    def read(action):
        try:
            return action()
        except (OSError, ValueError, KeyError, TypeError, RecursionError):
            # Never echo raw filesystem errors, credentials or unauthorized IDs.
            return jsonify(error='证据缺失、身份不一致或路径不在授权范围内。'), 404

    @app.get('/inspector')
    def inspector_page():
        return render_template('inspector.html', embedded=integrated and request.args.get('embedded') == '1',
                               execution_mode=execution_mode, execution_notice=notices[execution_mode])

    @app.get('/inspector-assets/<name>')
    def inspector_static(name):
        if name not in ('inspector.js', 'inspector.css'):
            abort(404)
        return send_file(Path(app.root_path) / 'static' / name)

    @app.get('/api/inspector/tasks')
    def inspector_tasks():
        return read(lambda: jsonify(tasks=reader.tasks()))

    if integrated:
        @app.get('/api/inspector/access')
        def inspector_access():
            identity = request.args.get('task_id', '')
            if len(identity) != 32 or any(c not in '0123456789abcdef' for c in identity):
                identity = None
            # Checks the server-owned scope; the browser cannot expand it.
            return jsonify(**debug_config(identity))

    @app.get('/api/inspector/tasks/<task_id>')
    def inspector_evidence(task_id):
        if not reader.allows_task(task_id):
            return jsonify(error='当前 Task 未获调试授权。', code='TASK_NOT_AUTHORIZED'), 404
        return read(lambda: jsonify(reader.inspect(task_id, *selection())))

    @app.get('/api/inspector/tasks/<task_id>/assets/<key>')
    def inspector_asset(task_id, key):
        def image():
            data, mime = reader.asset(task_id, *selection(), key)
            return send_file(io.BytesIO(data), mimetype=mime, max_age=0)
        return read(image)

    if integrated:
        @app.context_processor
        def inspector_workspace():
            # UI visibility is only convenience; every API/file read rechecks scope.
            identity = (request.view_args or {}).get('session_id')
            return {'inspector_enabled': allow_runtime_tasks or reader.allows_task(identity), 'local_debug_enabled': True,
                    'workspace_read_only': read_only_workspace,
                    'local_debug_config': debug_config(identity)}

    return reader


def create_inspector_app(runtime_dir, allowed_task_ids):
    app = Flask('workflow_inspector', root_path=str(Path(__file__).resolve().parents[1]), static_folder=None)
    register_inspector_routes(app, runtime_dir, allowed_task_ids)
    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-dir', required=True, type=Path, help='Web runtime 根目录，包含 sessions/')
    parser.add_argument('--task-id', required=True, action='append', help='显式授权 Task ID；可重复指定')
    parser.add_argument('--port', type=int, default=8011)
    args = parser.parse_args()
    create_inspector_app(args.runtime_dir, args.task_id).run(host='127.0.0.1', port=args.port, debug=False)


if __name__ == '__main__':
    main()
