import hashlib
import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from zoneinfo import ZoneInfo

HK = ZoneInfo('Asia/Hong_Kong')
TRACKED = ('name', 'organizer', 'edition', 'registration_url', 'deadline',
           'deadline_original', 'deadline_timezone', 'competition_dates', 'eligibility',
           'eligibility_state', 'team_size', 'format', 'fees', 'prizes', 'status',
           'verification', 'source_changed', 'source_hash', 'official_url', 'source_url',
           'registration_state', 'registration_opens', 'relevance_score')


def now_utc():
    return datetime.now(timezone.utc)


def parse_date(value, tz=None):
    """ISO times require offsets or an explicit IANA zone; date-only stays unknown.

    Never interpret ambiguous abbreviations (CST, IST) or supply end-of-day times.
    Reject ambiguous/nonexistent DST wall times without a supplied UTC offset.
    """
    if not value or not re.search(r'[T ]\d{2}:\d{2}', value):
        return None
    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if dt.tzinfo is not None:
        return dt
    if not tz:
        raise ValueError('Timezone required for a wall-clock deadline')
    zone = ZoneInfo(tz)
    a, b = dt.replace(tzinfo=zone, fold=0), dt.replace(tzinfo=zone, fold=1)
    if a.utcoffset() != b.utcoffset():
        raise ValueError('Ambiguous or nonexistent local time: supply explicit offset')
    if a.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None) != dt:
        raise ValueError('Nonexistent local time')
    return a


def canonical_url(url):
    p = urlsplit(url.strip())
    host = (p.hostname or '').lower().removeprefix('www.')
    query = [(k, v) for k, v in parse_qsl(p.query) if not k.lower().startswith('utm_') and k not in ('fbclid', 'gclid')]
    return urlunsplit(('https', host, p.path.rstrip('/') or '/', urlencode(sorted(query)), ''))


def record_id(record):
    if record.get('series_id'):
        return record['series_id']
    return hashlib.sha256(canonical_url(record['official_url']).encode()).hexdigest()[:16]


def deduplicate(records):
    result = {}
    urls = {}
    for record in records:
        key = record_id(record)
        url = canonical_url(record['official_url'])
        key = urls.get(url, key)
        if key not in result or (record.get('verification') == 'verified' and result[key].get('verification') != 'verified'):
            result[key] = dict(record, id=key)
        urls[url] = key
    return list(result.values())


def filter_record(record):
    """Hard exclusions are structured, reviewed decisions, never snippet guesses."""
    if record.get('excluded_reason'):
        return 'excluded'
    if record.get('level') == 'high_school_only' or record.get('meaningful_modelling') is False:
        return 'excluded'
    if record.get('eligibility_state') == 'ineligible':
        return 'excluded'
    if record.get('eligibility_state') != 'eligible':
        return 'manual_verification'
    return 'eligible'


def relevance(record):
    weights = {'modelling': 35, 'optimization': 20, 'probability': 15,
               'finance': 15, 'data': 10, 'interdisciplinary': 5}
    score = sum(weights.get(tag, 0) for tag in set(record.get('tags', [])))
    if record.get('level') == 'undergraduate':
        score += 10
    if record.get('format') == 'online':
        score += 5
    return min(100, score)


def deadline_days(record, now):
    dt = parse_date(record.get('deadline'))
    if dt is None:
        return None
    return (dt - now).total_seconds() / 86400


def decorate(record, now):
    record = dict(record)
    record['filter'] = filter_record(record)
    record['relevance_score'] = relevance(record)
    record['deadline_hkt'] = ''
    dt = parse_date(record.get('deadline'))
    if dt:
        record['deadline_hkt'] = dt.astimezone(HK).isoformat()
    # Do not turn missing dates into inferred deadlines or assume registration open.
    status = record.get('registration_state', 'unknown')
    if dt and dt < now:
        status = 'closed'
    elif record.get('verification') != 'verified':
        status = 'unknown'
    elif status == 'not_yet_open':
        opens = parse_date(record.get('registration_opens'))
        if opens and now >= opens:
            status = 'open'
    record['status'] = status
    days = deadline_days(record, now)
    record['actionable'] = (record['filter'] == 'eligible' and status == 'open'
                            and record.get('verification') == 'verified')
    record['deadline_alert'] = ('7 days' if days is not None and 0 <= days <= 7 else
                                '30 days' if days is not None and 0 <= days <= 30 else '') if record['actionable'] else ''
    return record


def changes(previous, current):
    old = {r['id']: r for r in previous}
    new, updated = [], []
    for r in current:
        if r['id'] not in old:
            new.append(r['id'])
        else:
            fields = [k for k in TRACKED if old[r['id']].get(k) != r.get(k)]
            if fields:
                updated.append({'id': r['id'], 'fields': fields})
    return new, updated


def load_json(path, default=None):
    p = Path(path)
    return json.loads(p.read_text()) if p.exists() else default


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    tmp.replace(path)
