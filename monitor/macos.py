"""Short-lived LaunchAgent checker. No Git checkout or background Python daemon."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
from datetime import timezone
import urllib.request
from urllib.parse import quote
from .core import atomic_json, load_json, now_utc, parse_date
from .notifier import deliver


def validate_manifest(manifest):
    if manifest.get('schema_version') != 1 or not isinstance(manifest.get('runs'), list):
        raise ValueError('Unsupported or malformed update manifest')
    if not isinstance(manifest.get('competitions', []), list):
        raise ValueError('Malformed competitions')
    for event in manifest['runs']:
        if not isinstance(event.get('id'), str) or not parse_date(event.get('completed_at')):
            raise ValueError('Run needs an ID and aware completion timestamp')
        for key in ('new', 'updated', 'upcoming'):
            if type(event.get(key)) is not int or event[key] < 0:
                raise ValueError('Invalid completion counters')
    return manifest


def plan(manifest, state, now, report_url=None):
    validate_manifest(manifest)
    seen = set(state.get('delivered', []))
    result = []
    url = report_url or manifest.get('report_url')
    # Replay every missed completion, including zero-result weeks. Past 7-day
    # alerts are not replayed: deadlines are calculated from the latest snapshot.
    for run in manifest['runs']:
        key = 'run:' + run['id']
        if key in seen or run.get('offline'):
            continue
        title = 'Math Modelling Monitor — ' + ('Weekly Update' if run.get('kind') == 'weekly' else 'Update')
        noun = "deadline" if run["upcoming"] == 1 else "deadlines"
        message = f"{run['new']} new competitions, {run['updated']} updated, {run['upcoming']} {noun} approaching."
        if run.get('high_relevance'):
            message += ' High relevance: ' + ', '.join(run['high_relevance'][:3]) + '.'
        if run.get('source_errors'):
            message += f" {run['source_errors']} source errors; check report."
        result.append({'key': key, 'title': title, 'message': message, 'url': url})
    generated = parse_date(manifest.get('generated_at'))
    # Stale snapshots do not trigger urgent alerts. Completion notifications above
    # remain deliverable after any length of shutdown.
    fresh = generated and 0 <= (now - generated).total_seconds() <= 14 * 86400
    if fresh and not manifest.get('offline'):
        for r in manifest.get('competitions', []):
            deadline = parse_date(r.get('deadline'))
            if not r.get('actionable') or not deadline:
                continue
            seconds = (deadline - now).total_seconds()
            key = 'deadline:' + r['id'] + ':' + deadline.astimezone(timezone.utc).isoformat()
            if 0 <= seconds <= 7 * 86400 and key not in seen:
                result.append({'key': key, 'title': 'Math Modelling Monitor — Deadline within 7 days',
                               'message': 'Registration: ' + r['name'] + ' closes ' + (r.get('deadline_hkt') or deadline.isoformat()) + ' (Hong Kong).', 'url': url})
    return result


def fetch_manifest(repo, branch='monitor-data', token=None):
    if not re.fullmatch(r'[\w.-]+/[\w.-]+', repo):
        raise ValueError('--repo must be OWNER/REPO')
    url = f'https://api.github.com/repos/{repo}/contents/data/updates.json?ref={quote(branch, safe="")}'
    headers = {'Accept': 'application/vnd.github.raw+json', 'User-Agent': 'MathCompetitionMonitor/1.0',
               'X-GitHub-Api-Version': '2022-11-28'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=20) as response:
        body = response.read(5_000_001)
        if len(body) > 5_000_000:
            raise ValueError('Manifest exceeds 5 MB limit')
        return json.loads(body)


def process(manifest, state_path, now, sender, dry_run=False, report_url=None):
    state = load_json(state_path, {'schema_version': 1, 'delivered': []})
    if state.get('schema_version') != 1 or not isinstance(state.get('delivered'), list):
        raise ValueError('Invalid notification state; restore backup or move file aside')
    events = plan(manifest, state, now, report_url)
    for event in events:
        if dry_run:
            print(json.dumps(event, ensure_ascii=False))
            continue
        sender(event)
        state['delivered'].append(event['key'])
        # Commit after each accepted notification. A failed sender is retried next
        # time; an already successful earlier event is not retried with it.
        atomic_json(state_path, state)
    return events


def main():
    p = argparse.ArgumentParser(description=__doc__)
    source = p.add_mutually_exclusive_group(required=True)
    source.add_argument('--repo')
    source.add_argument('--manifest', type=Path, help='Local JSON, for mocks and integration tests')
    p.add_argument('--branch', default='monitor-data')
    p.add_argument('--state-dir', type=Path, default=Path.home() / 'Library/Application Support/MathModellingMonitor')
    p.add_argument('--dry-run', action='store_true', help='Print planned notifications without sending or acknowledging')
    p.add_argument('--backend', choices=['auto', 'osascript', 'terminal-notifier'], default='auto')
    p.add_argument('--notifier-path', help='Absolute terminal-notifier path; useful for LaunchAgent PATH')
    p.add_argument('--report-url', help='Trusted override; HTTPS or local file URI')
    args = p.parse_args()
    args.state_dir.mkdir(parents=True, exist_ok=True)
    # Serialize concurrent manual checks and launchd invocations for this state dir.
    with (args.state_dir / '.lock').open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        manifest = load_json(args.manifest) if args.manifest else fetch_manifest(args.repo, args.branch, os.environ.get('MONITOR_GITHUB_TOKEN'))
        namespace = args.repo or str(args.manifest.resolve())
        state_path = args.state_dir / ('seen-' + hashlib.sha256(namespace.encode()).hexdigest()[:16] + '.json')
        report_url = args.report_url or (f'https://github.com/{args.repo}/blob/{quote(args.branch, safe="")}/data/report.md' if args.repo else None)
        process(manifest, state_path, now_utc(), lambda e: deliver(e, args.backend, args.notifier_path), args.dry_run, report_url)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        # Do not leak credentials or full response bodies into LaunchAgent logs.
        raise SystemExit(f'Notification check failed ({type(error).__name__}): {error}')
