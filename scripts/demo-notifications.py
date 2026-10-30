#!/usr/bin/env python3
"""Synthetic-only demonstration; no network or native delivery."""
from datetime import timedelta
import json
from pathlib import Path
from zoneinfo import ZoneInfo
import sys
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from monitor.core import now_utc
from monitor.macos import process

now = now_utc()
deadline = (now + timedelta(days=5)).astimezone(ZoneInfo('Asia/Hong_Kong')).isoformat()
manifest = {'schema_version': 1, 'generated_at': now.isoformat(),
    'report_url': 'https://example.org/SYNTHETIC-report',
    'runs': [{'id': 'SYNTHETIC-weekly-1', 'kind': 'weekly', 'completed_at': now.isoformat(),
              'new': 3, 'updated': 2, 'upcoming': 1,
              'high_relevance': ['SYNTHETIC Optimization Challenge']}],
    'competitions': [{'id': 'SYNTHETIC-contest', 'name': 'SYNTHETIC Optimization Challenge',
                      'deadline': deadline, 'deadline_hkt': deadline, 'actionable': True}]}
with tempfile.TemporaryDirectory() as directory:
    path = Path(directory) / 'state.json'
    sender = lambda event: print(json.dumps(event, ensure_ascii=False, indent=2))
    first = process(manifest, path, now, sender)
    second = process(manifest, path, now, sender)
    assert len(first) == 2 and not second
    print('PASS: 2 simulated notifications; second check: 0 duplicates. No real notifications sent.')
