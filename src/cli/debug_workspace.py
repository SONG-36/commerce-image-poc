"""Explicit local workspace + read-only Inspector; never a pilot/WSGI default."""

import argparse
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import subprocess
import time
import urllib.request


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_project_key(root, environment=None):
    """Load only a literal OPENAI_API_KEY; never execute or expand dotenv text."""
    environment = os.environ if environment is None else environment
    if environment.get('OPENAI_API_KEY', '').strip():
        return True
    path = Path(root) / '.env'
    if path.is_symlink():
        raise ValueError('.env 必须是项目根目录中的普通文件。')
    value = ''
    if path.exists():
        try:
            with path.open(encoding='utf-8-sig') as stream:
                text = stream.read(65537)
            if len(text) > 65536:
                raise ValueError()
            for line in text.splitlines():
                match = re.match(r'^\s*(?:export\s+)?OPENAI_API_KEY\s*=\s*(.*)$', line)
                if not match:
                    continue
                words = shlex.split(match.group(1), comments=True, posix=True)
                if len(words) > 1:
                    raise ValueError()
                value = words[0] if words else ''
                if any(c.isspace() or c in '$`\x00' for c in value):
                    raise ValueError()
        except (OSError, UnicodeError, ValueError):
            raise ValueError('.env 中的 OPENAI_API_KEY 格式无效；请填写单个值，不使用变量或命令。') from None
    environment['OPENAI_API_KEY'] = value
    return bool(value)


def _listener_pids(port):
    executable = shutil.which('lsof')
    if not executable:
        raise ValueError('缺少 lsof，无法安全核对端口归属；未停止任何服务。')
    result = subprocess.run([executable, '-nP', '-t', f'-iTCP:{port}', '-sTCP:LISTEN'],
                            capture_output=True, text=True, timeout=5)
    if result.returncode not in (0, 1) or any(not row.isdigit() for row in result.stdout.splitlines()):
        raise ValueError('无法安全核对监听进程；未停止任何服务。')
    return {int(row) for row in result.stdout.splitlines()}


def _process_identity(pid, args, root):
    def ps(field):
        result = subprocess.run(['ps', '-p', str(pid), '-o', field + '='],
                                capture_output=True, text=True, check=True, timeout=5)
        return result.stdout.strip()
    command = ps('args')
    words = shlex.split(command)
    def option(name):
        if name in words:
            return words[words.index(name) + 1]
        return next(word.split('=', 1)[1] for word in words if word.startswith(name + '='))
    cwd = subprocess.run([shutil.which('lsof'), '-a', '-p', str(pid), '-d', 'cwd', '-Fn'],
                         capture_output=True, text=True, check=True, timeout=5).stdout
    locations = [line[1:] for line in cwd.splitlines() if line.startswith('n')]
    if (pid == os.getpid() or ps('uid') != str(os.getuid()) or
            words[words.index('-m') + 1] != 'cli.debug_workspace' or
            Path(option('--runtime-dir')).resolve() != Path(args.runtime_dir).resolve() or
            option('--port') != str(args.port) or
            not locations or Path(locations[0]).resolve() != root.resolve()):
        raise ValueError('8013 端口归属不符合本项目调试入口；未停止该进程。')
    return command, ps('lstart'), locations[0]


def _server_json(port, path):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(f'http://127.0.0.1:{port}' + path, timeout=3) as response:
        return json.loads(response.read(1024 * 1024))


def replace_existing_debug_server(args, root):
    """Replace only the verified, idle local 8013 instance; never kill a stranger."""
    if args.port != 8013:
        raise ValueError('自动替换仅允许本地 8013，不会停止 8012 或其他端口。')
    pids = _listener_pids(args.port)
    if not pids:
        return
    if len(pids) != 1:
        raise ValueError('8013 存在多个监听进程；未停止任何服务。')
    pid = pids.pop()
    try:
        identity = _process_identity(pid, args, root)
        config = _server_json(args.port, '/api/inspector/access')
        if (config.get('pid') != pid or config.get('mode') != 'LIVE DEBUG' or
                Path(config.get('runtime_dir', '')).resolve() != Path(args.runtime_dir).resolve()):
            raise ValueError()
        if config.get('busy'):
            raise RuntimeError('8013 有业务操作正在运行；请等待完成后重新执行启动命令。')
        tasks = _server_json(args.port, '/api/tasks')['tasks']
        for task in tasks:
            if not re.fullmatch(r'[0-9a-f]{32}', task['id']):
                raise ValueError()
            state = _server_json(args.port, '/api/sessions/' + task['id'] + '/workspace')
            if ((state.get('activity') or {}).get('status') == 'RUNNING' or
                    any(card['status'] == 'RUNNING' for card in state['generation']['cards'])):
                raise RuntimeError('8013 有 AI 操作正在运行；请等待完成后重新执行启动命令。')
        if _process_identity(pid, args, root) != identity:
            raise ValueError()
    except RuntimeError:
        raise
    except (OSError, ValueError, KeyError, IndexError, StopIteration, TypeError, subprocess.SubprocessError):
        raise ValueError('无法确认 8013 进程身份、Runtime 或运行状态；端口冲突，未停止该进程。') from None
    os.kill(pid, signal.SIGTERM)
    for _ in range(30):
        if not _listener_pids(args.port):
            return
        time.sleep(0.1)
    raise ValueError('旧 8013 服务尚未退出；未强制终止，请稍后重试。')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-dir', required=True, type=Path, help='独立本地调试 Runtime，包含 sessions/')
    parser.add_argument('--task-id', action='append', default=[], help='可选的初始任务链接；本地任务不需逐项授权')
    parser.add_argument('--port', type=int, default=8012)
    parser.add_argument('--allow-paid-actions', action='store_true',
                        help='允许用户点击触发真实模型；未配置 Key 时仍保持禁用')
    parser.add_argument('--replace-existing', action='store_true', help='仅替换身份已核实且空闲的本项目 8013')
    args = parser.parse_args()
    from app import create_local_debug_app
    try:
        configured = load_project_key(PROJECT_ROOT)
        application = create_local_debug_app(args.runtime_dir, args.task_id, execution_mode='LIVE DEBUG',
                                              allow_paid_actions=bool(args.allow_paid_actions and configured),
                                              allow_runtime_tasks=True)
        if args.replace_existing:
            replace_existing_debug_server(args, PROJECT_ROOT)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        parser.error(str(error))
    print(f'LIVE DEBUG · Key configured: {configured} · 不自动调用模型', flush=True)
    initial_page = '/workspace/' + args.task_id[0] if args.task_id else '/'
    print(f'http://127.0.0.1:{args.port}' + initial_page, flush=True)
    application.run(host='127.0.0.1', port=args.port, debug=False, threaded=True, use_reloader=False,
                    load_dotenv=False)


if __name__ == '__main__':
    main()
