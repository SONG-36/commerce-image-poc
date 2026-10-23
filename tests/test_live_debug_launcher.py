"""One-command local launcher: temporary dotenv files, mocked processes, no network."""

import argparse
import contextlib
import io
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from cli import debug_workspace as launcher


TASK = 'a' * 32


class LiveLauncherTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.environment = {}

    def write_env(self, value):
        (self.root / '.env').write_text(value, encoding='utf-8')

    def test_missing_empty_and_whitespace_key_remain_disabled(self):
        self.assertFalse(launcher.load_project_key(self.root, self.environment))
        for text in ('OPENAI_API_KEY=\n', 'OPENAI_API_KEY=""\n', '# no Key\n'):
            self.write_env(text)
            self.environment['OPENAI_API_KEY'] = '  '
            self.assertFalse(launcher.load_project_key(self.root, self.environment))
            self.assertEqual(self.environment['OPENAI_API_KEY'], '')

    def test_load_only_literal_key_and_ignore_example_and_shell_expressions(self):
        (self.root / '.env.example').write_text('OPENAI_API_KEY=not-a-real-example\n')
        self.assertFalse(launcher.load_project_key(self.root, self.environment))
        marker = self.root / 'must-not-exist'
        self.write_env(f'UNRELATED=$(touch {marker})\nexport OPENAI_API_KEY="offline-canary" # comment\n')
        self.assertTrue(launcher.load_project_key(self.root, self.environment))
        self.assertEqual(self.environment['OPENAI_API_KEY'], 'offline-canary')
        self.assertFalse(marker.exists())

    def test_existing_nonempty_environment_wins_without_reading_dotenv(self):
        self.write_env('OPENAI_API_KEY=\n')
        self.environment['OPENAI_API_KEY'] = 'existing-offline-value'
        with patch.object(Path, 'open', side_effect=AssertionError('Must not read dotenv')):
            self.assertTrue(launcher.load_project_key(self.root, self.environment))
        self.assertEqual(self.environment['OPENAI_API_KEY'], 'existing-offline-value')

    def test_invalid_values_are_rejected_without_echoing_or_executing_them(self):
        for value in ('"unterminated-offline-value', '$(touch must-not-exist)', '`command`', 'two values'):
            self.write_env('OPENAI_API_KEY=' + value + '\n')
            self.environment.clear()
            with self.assertRaises(ValueError) as caught:
                launcher.load_project_key(self.root, self.environment)
            self.assertNotIn(value, str(caught.exception))

    def test_symlink_dotenv_is_rejected(self):
        target = self.root / 'other'
        target.write_text('OPENAI_API_KEY=offline-only\n')
        (self.root / '.env').symlink_to(target)
        with self.assertRaises(ValueError):
            launcher.load_project_key(self.root, self.environment)

    def test_main_starts_with_effective_key_gate_without_key_in_output_or_arguments(self):
        import app
        for value, enabled in [('', False), ('offline-canary-not-a-real-key', True)]:
            self.write_env('OPENAI_API_KEY=' + value + '\n')
            output = io.StringIO()
            with patch.dict(os.environ, {'OPENAI_API_KEY': ''}), \
                    patch.object(launcher, 'PROJECT_ROOT', self.root), \
                    patch.object(sys, 'argv', ['debug_workspace', '--runtime-dir', str(self.root / 'runtime'),
                                              '--task-id', TASK, '--port', '8013', '--allow-paid-actions']), \
                    patch.object(app, 'create_local_debug_app') as factory, contextlib.redirect_stdout(output):
                launcher.main()
                self.assertEqual(factory.call_args.kwargs['allow_paid_actions'], enabled)
                self.assertEqual(factory.call_args.kwargs['execution_mode'], 'LIVE DEBUG')
                self.assertTrue(factory.call_args.kwargs['allow_runtime_tasks'])
                factory.return_value.run.assert_called_once_with(host='127.0.0.1', port=8013,
                                                                 debug=False, threaded=True, use_reloader=False,
                                                                 load_dotenv=False)
            self.assertNotIn('offline-canary', output.getvalue())
            self.assertFalse((self.root / 'runtime').exists())

    def test_script_has_fixed_arguments_and_never_creates_missing_runtime(self):
        script = Path(__file__).resolve().parents[1] / 'scripts/start_live_debug.sh'
        (self.root / 'scripts').mkdir()
        copied = self.root / 'scripts/start_live_debug.sh'
        copied.write_bytes(script.read_bytes())
        executable = self.root / '.venv/bin/python'
        executable.parent.mkdir(parents=True)
        executable.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$ARG_CAPTURE"\n')
        executable.chmod(0o700)
        runtime = self.root / '.runtime/debug/live-debug-20261023T013447Z/runtime'
        output = self.root / 'arguments'
        env = {**os.environ, 'OPENAI_API_KEY': '', 'ARG_CAPTURE': str(output)}
        result = subprocess.run(['sh', str(copied)], env=env, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(runtime.exists())
        runtime.mkdir(parents=True)
        result = subprocess.run(['sh', str(copied)], env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(output.read_text().splitlines(), ['-B', '-m', 'cli.debug_workspace',
            '--runtime-dir', str(runtime), '--port', '8013',
            '--allow-paid-actions', '--replace-existing'])

    def test_process_identity_requires_same_user_project_directory_and_exact_module_arguments(self):
        args = argparse.Namespace(runtime_dir=self.root / 'runtime', port=8013)
        values = {'cwd': str(self.root), 'args': f'python -B -m cli.debug_workspace --runtime-dir {args.runtime_dir} --port 8013'}
        def run(command, **kwargs):
            if command[0] == 'ps':
                field = command[-1]
                output = {'args=': values['args'], 'uid=': str(os.getuid()), 'lstart=': 'fixed-start'}[field]
            else:
                output = 'p99901\nn' + values['cwd'] + '\n'
            return subprocess.CompletedProcess(command, 0, stdout=output, stderr='')
        with patch.object(launcher.subprocess, 'run', side_effect=run), patch.object(launcher.shutil, 'which', return_value='lsof'):
            self.assertEqual(launcher._process_identity(99901, args, self.root)[1], 'fixed-start')
            values['cwd'] = str(self.root / 'other')
            with self.assertRaises(ValueError):
                launcher._process_identity(99901, args, self.root)
            values['cwd'] = str(self.root)
            values['args'] = f'python -B -m another_app --runtime-dir {args.runtime_dir} --port 8013'
            with self.assertRaises(ValueError):
                launcher._process_identity(99901, args, self.root)


class ReplaceDebugProcessTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.args = argparse.Namespace(runtime_dir=self.root / 'runtime', task_id=[TASK], port=8013)
        self.pid = 99901
        self.config = {'pid': self.pid, 'mode': 'LIVE DEBUG', 'authorized': True,
                       'runtime_dir': str(self.args.runtime_dir)}
        self.busy = False
        self.listener = self.enterContext(patch.object(launcher, '_listener_pids', side_effect=[{self.pid}, set()]))
        self.identity = self.enterContext(patch.object(launcher, '_process_identity', return_value=('command', 'start', 'cwd')))
        self.enterContext(patch.object(launcher, '_server_json', side_effect=self.server_json))
        self.kill = self.enterContext(patch.object(launcher.os, 'kill'))
        self.enterContext(patch.object(launcher.time, 'sleep'))

    def server_json(self, port, path):
        if path.startswith('/api/inspector/access'):
            return self.config
        if path == '/api/tasks':
            return {'tasks': [{'id': TASK}]}
        return {'activity': None, 'generation': {'cards': [{'status': 'RUNNING' if self.busy else 'NOT_STARTED'}]}}

    def test_verified_idle_server_only_receives_sigterm(self):
        launcher.replace_existing_debug_server(self.args, self.root)
        self.kill.assert_called_once_with(self.pid, signal.SIGTERM)
        self.assertEqual(self.identity.call_count, 2)

    def test_unused_port_does_not_kill_any_process(self):
        self.listener.side_effect = [set()]
        launcher.replace_existing_debug_server(self.args, self.root)
        self.kill.assert_not_called()

    def test_8012_is_never_stopped(self):
        self.args.port = 8012
        with self.assertRaises(ValueError):
            launcher.replace_existing_debug_server(self.args, self.root)
        self.kill.assert_not_called()
        self.listener.assert_not_called()

    def test_unknown_process_is_not_stopped(self):
        self.identity.side_effect = ValueError('unknown owner')
        with self.assertRaises(ValueError):
            launcher.replace_existing_debug_server(self.args, self.root)
        self.kill.assert_not_called()

    def test_foreign_runtime_or_mock_is_not_stopped(self):
        original = dict(self.config)
        for change in ({'runtime_dir': str(self.root / 'other')}, {'mode': 'MOCK'}):
            self.listener.side_effect = [{self.pid}]
            self.config = {**original, **change}
            with self.assertRaises(ValueError):
                launcher.replace_existing_debug_server(self.args, self.root)
            self.kill.assert_not_called()

    def test_verified_runtime_can_restart_without_a_fixed_task_or_task_grant(self):
        self.args.task_id = []
        self.config['authorized'] = False  # Metadata request has no Task selection.
        launcher.replace_existing_debug_server(self.args, self.root)
        self.kill.assert_called_once_with(self.pid, signal.SIGTERM)

    def test_main_needs_no_task_argument_and_reports_task_center(self):
        import app
        with patch.dict(os.environ, {'OPENAI_API_KEY': ''}), \
                patch.object(launcher, 'PROJECT_ROOT', self.root), \
                patch.object(sys, 'argv', ['debug_workspace', '--runtime-dir', str(self.root), '--port', '8013']), \
                patch.object(app, 'create_local_debug_app') as factory, \
                patch('builtins.print') as output:
            launcher.main()
        self.assertEqual(factory.call_args.args[1], [])
        self.assertTrue(factory.call_args.kwargs['allow_runtime_tasks'])
        output.assert_any_call('http://127.0.0.1:8013/', flush=True)

    def test_running_model_is_not_interrupted(self):
        self.busy = True
        with self.assertRaises(RuntimeError):
            launcher.replace_existing_debug_server(self.args, self.root)
        self.kill.assert_not_called()

    def test_server_reported_business_lock_prevents_restart(self):
        self.config['busy'] = True
        with self.assertRaises(RuntimeError):
            launcher.replace_existing_debug_server(self.args, self.root)
        self.kill.assert_not_called()

    def test_changed_identity_and_multiple_listeners_are_not_stopped(self):
        self.identity.side_effect = [('old',), ('new',)]
        with self.assertRaises(ValueError):
            launcher.replace_existing_debug_server(self.args, self.root)
        self.kill.assert_not_called()
        self.listener.side_effect = [{self.pid, self.pid + 1}]
        with self.assertRaises(ValueError):
            launcher.replace_existing_debug_server(self.args, self.root)
        self.kill.assert_not_called()

    def test_no_forced_kill_when_old_server_does_not_exit(self):
        self.listener.side_effect = lambda port: {self.pid}
        with self.assertRaises(ValueError):
            launcher.replace_existing_debug_server(self.args, self.root)
        self.kill.assert_called_once_with(self.pid, signal.SIGTERM)


if __name__ == '__main__':
    unittest.main()
