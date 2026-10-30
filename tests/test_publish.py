"""Exercise the same data-branch publication script used by Actions, locally."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('git'), 'git not available')
class Publication(unittest.TestCase):
    def test_initial_publish_and_restore_then_append(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo, remote = root / 'source', root / 'remote.git'
            repo.mkdir()
            def call(*args, cwd=repo):
                return subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True).stdout
            call('git', 'init', '--bare', str(remote), cwd=root)
            call('git', 'init', '-b', 'main')
            call('git', 'config', 'user.name', 'Test')
            call('git', 'config', 'user.email', 'test@example.org')
            (repo / 'source.txt').write_text('source code')
            call('git', 'add', '.')
            call('git', 'commit', '-m', 'source')
            call('git', 'remote', 'add', 'origin', str(remote))
            call('git', 'push', '-u', 'origin', 'main')
            (repo / 'data').mkdir()
            (repo / 'data/updates.json').write_text('{"runs": [1]}')
            call('bash', str(ROOT / 'scripts/publish.sh'))
            first = call('git', 'rev-parse', 'refs/remotes/origin/monitor-data').strip()
            self.assertEqual(json.loads(call('git', 'show', first + ':data/updates.json'))['runs'], [1])
            self.assertEqual(call('git', 'ls-tree', '--name-only', first).strip(), 'data')
            # Reproduce a clean second Actions checkout.
            call('git', 'worktree', 'remove', '--force', 'work/publish')
            shutil.rmtree(repo / 'data')
            call('git', 'fetch', 'origin', 'monitor-data')
            call('git', 'restore', '--source=FETCH_HEAD', '--worktree', '--', 'data')
            restored = json.loads((repo / 'data/updates.json').read_text())
            restored['runs'].append(2)
            (repo / 'data/updates.json').write_text(json.dumps(restored))
            call('bash', str(ROOT / 'scripts/publish.sh'))
            second = call('git', 'rev-parse', 'refs/remotes/origin/monitor-data').strip()
            self.assertEqual(call('git', 'rev-parse', second + '^').strip(), first)
            self.assertEqual(json.loads(call('git', 'show', second + ':data/updates.json'))['runs'], [1, 2])
            self.assertEqual(call('git', 'branch', '--show-current').strip(), 'main')
