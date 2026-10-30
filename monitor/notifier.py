"""Native delivery adapter; arguments never pass through a shell."""
import platform
import shutil
import subprocess
from urllib.parse import urlsplit

APPLESCRIPT = '''on run argv
    display notification (item 2 of argv) with title (item 1 of argv)
end run'''


def command(title, message, url, group, backend='auto', executable=None):
    notifier = executable or shutil.which('terminal-notifier')
    if backend == 'terminal-notifier' and not notifier:
        raise RuntimeError('Install optional terminal-notifier or use --backend osascript')
    if notifier and backend in ('auto', 'terminal-notifier'):
        args = [notifier, '-title', title, '-message', message, '-group', group]
        # The downloaded manifest cannot inject arbitrary custom URI handlers.
        if url and urlsplit(url).scheme in ('https', 'file'):
            args += ['-open', url]
        return args
    return ['/usr/bin/osascript', '-e', APPLESCRIPT, title, message]


def deliver(event, backend='auto', executable=None):
    if platform.system() != 'Darwin':
        raise RuntimeError('Native delivery requires macOS; use --dry-run elsewhere')
    subprocess.run(command(event['title'], event['message'], event.get('url'),
                           event['key'], backend, executable), check=True, timeout=20,
                   capture_output=True, text=True)
