"""Install only on explicit invocation. Preview mode never touches launchd."""
import argparse
import os
from pathlib import Path
import platform
import plistlib
import re
import shutil
import subprocess
import sys

LABEL = 'org.mathmodelling.monitor'


def launchagent(python, runtime, state_dir, repo, notifier=None, interval=3600):
    args = [str(python), '-m', 'monitor.macos', '--repo', repo, '--state-dir', str(state_dir)]
    if notifier:
        args += ['--notifier-path', str(notifier)]
    return {'Label': LABEL, 'ProgramArguments': args, 'WorkingDirectory': str(runtime),
            'RunAtLoad': True, 'StartInterval': interval, 'ProcessType': 'Background',
            'LimitLoadToSessionType': 'Aqua',
            'StandardOutPath': str(state_dir / 'checker.log'),
            'StandardErrorPath': str(state_dir / 'checker-errors.log'),
            'EnvironmentVariables': {'PATH': '/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin'}}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo', required=True, help='Public GitHub OWNER/REPO')
    p.add_argument('--preview-dir', type=Path, help='Write installation preview here; do not install or start')
    p.add_argument('--interval', type=int, default=3600, help='Seconds between checks (minimum 900)')
    args = p.parse_args()
    if not re.fullmatch(r'[\w.-]+/[\w.-]+', args.repo):
        p.error('--repo must be OWNER/REPO')
    if args.interval < 900:
        p.error('Use at least 900 seconds to limit background traffic')
    if not args.preview_dir and platform.system() != 'Darwin':
        p.error('Installation requires macOS')
    if args.preview_dir:
        state_dir = args.preview_dir.resolve() / 'MathModellingMonitor'
        agent_dir = args.preview_dir.resolve() / 'LaunchAgents'
    else:
        state_dir = Path.home() / 'Library/Application Support/MathModellingMonitor'
        agent_dir = Path.home() / 'Library/LaunchAgents'
    state_dir.mkdir(parents=True, exist_ok=True)
    state_dir.chmod(0o700)
    agent_dir.mkdir(parents=True, exist_ok=True)
    runtime = state_dir / 'runtime'
    runtime.mkdir(exist_ok=True)
    shutil.copytree(Path(__file__).parent, runtime / 'monitor', dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    plist = agent_dir / (LABEL + '.plist')
    value = launchagent(Path(sys.executable).resolve(), runtime, state_dir, args.repo,
                        shutil.which('terminal-notifier'), args.interval)
    plist.write_bytes(plistlib.dumps(value))
    plist.chmod(0o600)
    print('Wrote ' + str(plist))
    if not args.preview_dir:
        domain = 'gui/' + str(os.getuid())
        subprocess.run(['/bin/launchctl', 'bootout', domain, str(plist)], capture_output=True)
        subprocess.run(['/bin/launchctl', 'bootstrap', domain, str(plist)], check=True)
        print('Enabled hourly checks and login catch-up. No persistent Python process.')
    else:
        print('Preview only: no LaunchAgent was loaded and no notifications were sent.')


if __name__ == '__main__':
    main()
