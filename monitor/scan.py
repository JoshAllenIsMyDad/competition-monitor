"""Run with python3 -m monitor.scan --help."""
import argparse
import fcntl
import hashlib
import os
from pathlib import Path
from .core import (atomic_json, changes, decorate, deduplicate, load_json,
                   now_utc, parse_date, record_id)
from .report import csv_text, render
from .sources import Fetcher, discover, verify


def run(root, output, now, offline=False, run_id=None, kind='manual', repo=None):
    output.mkdir(parents=True, exist_ok=True)
    with (output / '.scan.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        old_state = load_json(output / 'state.json', {'records': []})
        previous = old_state['records']
        old_by_id = {r['id']: r for r in previous}
        catalog = load_json(root / 'config/catalog.json')
        config = load_json(root / 'config/sources.json')
        fetcher = Fetcher()
        records = []
        for r in catalog:
            r = dict(r, id=record_id(r))
            if not offline and not r.get('excluded_reason'):
                r = verify(r, fetcher, now, old_by_id.get(r['id']))
            records.append(r)
        leads = [] if offline else discover(config, fetcher)
        # Catalog wins; a lead never overwrites reviewed facts. Missing competitions
        # stay in history instead of disappearing on a failed feed or search request.
        current = deduplicate(records + previous + leads)
        current = [decorate(r, now) for r in current]
        new, updated = changes(previous, current)
        mode = 'OFFLINE RESEARCH BASELINE — no live requests' if offline else 'LIVE — guarded official sources and discovery leads'
        report = render(current, new, updated, now, fetcher.errors, mode)
        (output / 'report.md').write_text(report)
        (output / 'competitions.csv').write_text(csv_text(current), encoding='utf-8-sig')
        run_id = run_id or now.isoformat()
        event = {'id': run_id, 'completed_at': now.isoformat(), 'kind': kind,
                 'new': len([r for r in current if r['id'] in new and r['filter'] != 'excluded']),
                 'updated': len([c for c in updated if next(r for r in current if r['id'] == c['id'])['filter'] != 'excluded']),
                 'upcoming': sum(bool(r['deadline_alert']) for r in current),
                 'high_relevance': [r['name'] for r in current if r['id'] in new and r['relevance_score'] >= 80 and r['actionable']],
                 'source_errors': len(fetcher.errors), 'offline': offline,
                 'report_sha256': hashlib.sha256(report.encode()).hexdigest()}
        manifest = load_json(output / 'updates.json', {'schema_version': 1, 'runs': []})
        # Idempotent CI reruns: same GitHub run ID never creates another completion.
        if not any(e['id'] == run_id for e in manifest['runs']):
            manifest['runs'].append(event)
        manifest['generated_at'] = now.isoformat()
        manifest['offline'] = offline
        manifest['competitions'] = [
            {k: r.get(k) for k in ('id', 'name', 'deadline', 'deadline_hkt', 'actionable', 'relevance_score', 'verification', 'last_verified')}
            for r in current if r['filter'] != 'excluded']
        if repo:
            manifest['report_url'] = f'https://github.com/{repo}/blob/monitor-data/data/report.md'
        atomic_json(output / 'state.json', {'schema_version': 1, 'records': current})
        atomic_json(output / 'history' / (hashlib.sha256(run_id.encode()).hexdigest()[:20] + '.json'),
                    {'event': event, 'changes': updated, 'records': current, 'errors': fetcher.errors})
        # Completion manifest written last. CI publishes all output in one commit.
        atomic_json(output / 'updates.json', manifest)
        return event


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, default=Path('data'))
    p.add_argument('--offline', action='store_true', help='Use researched baseline; no live verification or discovery')
    p.add_argument('--as-of', help='Explicit aware ISO time for reproducible offline samples only')
    p.add_argument('--run-id', default=os.environ.get('GITHUB_RUN_ID'))
    p.add_argument('--kind', choices=['weekly', 'manual'], default='manual')
    args = p.parse_args()
    if args.as_of and not args.offline:
        p.error('--as-of is for offline demonstrations only')
    now = parse_date(args.as_of) if args.as_of else now_utc()
    if now is None:
        p.error('Invalid --as-of')
    event = run(Path(__file__).resolve().parents[1], args.output, now,
                args.offline, args.run_id, args.kind, os.environ.get('GITHUB_REPOSITORY'))
    print(event)


if __name__ == '__main__':
    main()
