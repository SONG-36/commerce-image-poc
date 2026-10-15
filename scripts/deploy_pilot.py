"""Deploy explicitly selected committed files to the existing Mac mini pilot.

Default is read-only preflight. --apply backs up code, creates a separate release,
checks idle runs, and restarts only this LaunchAgent. No model calls or Git push.
"""

import argparse
import base64
import hashlib
import json
from pathlib import Path, PurePosixPath
import shlex
import subprocess


REMOTE = r'''
import ast, base64, fcntl, hashlib, json, os, plistlib, re, ssl
import subprocess, sys, tarfile, time, urllib.request
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

p = json.load(sys.stdin)
base = Path(p['base'])
label = 'com.song36.commerce-image-pilot'
domain = 'gui/' + str(os.getuid())
plist = Path.home() / ('Library/LaunchAgents/' + label + '.plist')
original_plist = plist.read_bytes()
launch = plistlib.loads(original_plist)
assert launch['Label'] == label
assert not any('KEY' in k.upper() or 'SECRET' in k.upper() for k in launch.get('EnvironmentVariables', {})), 'Secret in LaunchAgent; refused.'
argv = launch['ProgramArguments']
old = Path(argv[argv.index('--chdir') + 1]).parent
assert old.parent == base / 'releases' and not old.is_symlink(), 'Unexpected source directory.'
manifest_file = old / '.pilot-source.json'
manifest = json.loads((manifest_file if manifest_file.exists() else base / 'config/source-manifest.json').read_text())

def digest(data): return hashlib.sha256(data).hexdigest()
def file_hashes(root):
    result = {}
    for path in sorted(root.rglob('*')):
        if path.is_symlink(): raise RuntimeError('Unexpected symlink; stopped.')
        if path.is_file(): result[str(path.relative_to(root))] = digest(path.read_bytes())
    return result

expected = {item['path']: item['sha256'] for item in manifest['files']}
for name in set(expected) | set(p['files']):
    relative = Path(name)
    assert not relative.is_absolute() and '..' not in relative.parts and '\\' not in name, 'Unsafe source path.'
actual = file_hashes(old)
extras = [name for name in actual if name not in expected and name != '.pilot-source.json'
          and '__pycache__' not in Path(name).parts]
assert not extras and all(actual.get(name) == value for name, value in expected.items()), 'Server has independent changes; stopped.'
files = {name: base64.b64decode(value, validate=True) for name, value in p['files'].items()}
for name, value in files.items():
    assert digest(value) == p['target_hashes'][name]
combined = {**expected, **{name: digest(value) for name, value in files.items()}}
required = set(expected) | {name for name in p['target_hashes'] if name.startswith(('src/', 'tests/'))}
assert all(combined.get(name) == p['target_hashes'].get(name) for name in required), 'Required changed files were not selected; stopped.'
tree = ast.parse(files.get('src/prepare_plan.py', (old / 'src/prepare_plan.py').read_bytes()))
models = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
              and any(isinstance(t, ast.Name) and t.id == 'MODELS' for t in n.targets))
assert p['model'] in models, 'Planning model not allowed by deployed source.'
data = base / 'data/.runtime'

def idle():
    for path in (data / 'prepare-plan/sessions').glob('*/**/run.json'):
        if json.loads(path.read_text()).get('status') in ['RUNNING', 'PREPARING']:
            raise RuntimeError('Active or unresolved AI run; stopped without restarting.')

idle()
print(json.dumps({'stage': 'PREFLIGHT_OK', 'old_release': str(old), 'commit': p['commit'],
                  'planning_model': p['model'], 'sync_files': list(files), 'apply': p['apply']}), flush=True)
if not p['apply']: sys.exit(0)
os.umask(0o077)
deployment_lock = (base / 'backups/.incremental-deploy.lock').open('a')
fcntl.flock(deployment_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid4().hex[:8]
backup = base / 'backups' / ('deploy-' + stamp)
backup.mkdir()
(backup / 'launchagent.plist').write_bytes(original_plist)
archive = backup / 'code.tar.gz'
with tarfile.open(archive, 'x:gz') as tar:
    for name in expected: tar.add(old / name, arcname=name, recursive=False)
with tarfile.open(archive) as tar:
    assert {entry.name: digest(tar.extractfile(entry).read()) for entry in tar} == expected
new = base / 'releases' / p['commit'] if files else old
if files:
    new.mkdir()  # Never overwrite an existing release.
    for name in combined:
        destination = new / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(files[name] if name in files else (old / name).read_bytes())
    (new / '.pilot-source.json').write_text(json.dumps({'commit': p['commit'], 'files': [
        {'path': name, 'sha256': value} for name, value in sorted(combined.items())]}, indent=2) + '\n')
    staged_hashes = file_hashes(new)
    assert all(staged_hashes.get(name) == value for name, value in combined.items())
    for path in (new / 'src').rglob('*.py'): compile(path.read_bytes(), str(path), 'exec')
    check = subprocess.run([str(base / 'venv/bin/python'), '-m', 'unittest', 'discover', '-s', 'tests', '-q'],
        cwd=new, env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'}, capture_output=True)
    if check.returncode: raise RuntimeError('Staged release offline tests failed; current service untouched.')
    print(json.dumps({'stage': 'STAGED_TESTS_PASS', 'code_backup': str(archive)}), flush=True)

def ctl(*args): subprocess.run(['launchctl', *args], check=True, stdout=subprocess.DEVNULL)
def healthy():
    settings = json.loads((base / 'config/settings.json').read_text())
    address = 'https://' + settings['host']
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
        urllib.request.HTTPSHandler(context=ssl.create_default_context(cafile=str(base / 'config/server.crt'))))
    with opener.open(address + '/', timeout=3) as response: assert response.status == 200
    with opener.open(address + '/api/tasks', timeout=3) as response:
        assert response.status == 200
        return json.load(response)

idle()
before_data = file_hashes(data)
before_config = file_hashes(base / 'config')  # In memory only; never record secret hashes.
assert plist.read_bytes() == original_plist, 'LaunchAgent changed during preflight.'
stopped = False
lease = None
try:
    ctl('bootout', domain, str(plist))
    stopped = True
    lease = (data / '.pilot-worker.lock').open('a')
    deadline = time.monotonic() + 250
    while True:
        try:
            fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except BlockingIOError:
            if time.monotonic() > deadline: raise RuntimeError('Old worker still owns data; no forced kill.')
            time.sleep(0.5)
    idle()
    assert file_hashes(data) == before_data, 'Business data changed during shutdown; deployment stopped.'
    launch['ProgramArguments'][argv.index('--chdir') + 1] = str(new / 'src')
    launch.setdefault('EnvironmentVariables', {})['OPENAI_PLANNING_MODEL'] = p['model']
    temporary = plist.with_suffix('.plist.deploy-tmp')
    with temporary.open('xb') as stream: plistlib.dump(launch, stream)
    temporary.replace(plist)
    lease.close()
    lease = None
    ctl('bootstrap', domain, str(plist))
    stopped = False
    deadline = time.monotonic() + 40
    while True:
        try:
            tasks = healthy()
            status = subprocess.check_output(['launchctl', 'print', domain + '/' + label], text=True)
            master = re.search(r'\n\s*pid = (\d+)', status).group(1)
            children = subprocess.check_output(['pgrep', '-P', master], text=True).split()
            assert children
            for pid in children:
                environment = subprocess.check_output(['ps', 'eww', '-p', pid, '-o', 'command='], text=True)
                configured = re.search(r'(?:^|\s)OPENAI_PLANNING_MODEL=([^\s]+)', environment)
                assert configured and configured.group(1) == p['model']
            break
        except Exception:
            if time.monotonic() > deadline: raise RuntimeError('HTTPS/process model verification failed.')
            time.sleep(1)
    assert file_hashes(data) == before_data, 'Business data changed; do not overwrite it.'
    assert file_hashes(base / 'config') == before_config, 'Server config changed unexpectedly.'
    record = {'commit': p['commit'], 'release': str(new), 'previous_release': str(old),
              'planning_model': p['model'], 'worker_pids': children, 'synced_files': list(files),
              'data_files_unchanged': len(before_data), 'config_unchanged': True,
              'code_backup': str(archive), 'launchagent_backup': str(backup / 'launchagent.plist'),
              'https': 'PASS', 'task_count': len(tasks['tasks']), 'paid_api_calls': 0,
              'real_model_validation': 'PENDING'}
    (backup / 'result.json').write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(record, ensure_ascii=False), flush=True)
except BaseException:
    if lease is not None: lease.close()
    if not stopped: ctl('bootout', domain, str(plist))
    plist.write_bytes(original_plist)
    ctl('bootstrap', domain, str(plist))
    print('Deployment failed; original LaunchAgent restored; business data not restored or overwritten.', file=sys.stderr)
    raise
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--server', default='andy_server@192.168.112.37')
    parser.add_argument('--base', default='/Users/andy_server/commerce-image-poc-pilot')
    parser.add_argument('--commit', default='HEAD')
    parser.add_argument('--file', action='append', default=[], help='Explicit tracked file to sync; repeatable.')
    parser.add_argument('--planning-model', required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]

    def git(*parts):
        return subprocess.check_output(['git', *parts], cwd=root)

    commit = git('rev-parse', '--verify', args.commit + '^{commit}').decode().strip()
    tracked = git('ls-tree', '-rz', commit).split(b'\0')
    hashes, modes = {}, {}
    for row in filter(None, tracked):
        meta, name = row.split(b'\t', 1)
        name = name.decode()
        mode, kind, oid = meta.decode().split()
        if kind == 'blob':
            hashes[name] = hashlib.sha256(git('cat-file', 'blob', oid)).hexdigest()
            modes[name] = mode
    files = {}
    for name in args.file:
        path = PurePosixPath(name)
        allowed = name.startswith(('src/', 'tests/')) or name in ['README.md', 'requirements.txt']
        if (not allowed or path.is_absolute() or '..' in path.parts or str(path) != name
                or modes.get(name) != '100644' or any(part.startswith('.') for part in path.parts)):
            parser.error('Only explicit ordinary source/test/README/requirements files are allowed.')
        content = git('show', commit + ':' + name)
        if (root / name).is_symlink() or (root / name).read_bytes() != content:
            parser.error('Selected file differs from the commit: ' + name)
        files[name] = base64.b64encode(content).decode()
    payload = {'base': args.base, 'commit': commit, 'model': args.planning_model,
               'files': files, 'target_hashes': hashes, 'apply': args.apply}
    command = [str(Path(args.base) / 'venv/bin/python'), '-c', REMOTE]
    subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ClearAllForwardings=yes', '-o', 'ConnectTimeout=10',
                    args.server, shlex.join(command)], input=json.dumps(payload).encode(), check=True)


if __name__ == '__main__':
    main()
