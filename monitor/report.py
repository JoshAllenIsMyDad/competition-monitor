import csv
import io
import json
from .core import HK, deadline_days

FIELDS = ['id', 'name', 'organizer', 'official_url', 'registration_url', 'category',
          'edition', 'description', 'techniques', 'eligibility', 'eligibility_state',
          'team_size', 'format', 'deadline_original', 'deadline_timezone', 'deadline',
          'deadline_hkt', 'competition_dates', 'fees', 'prizes', 'status',
          'last_verified', 'last_fetched', 'verification', 'relevance_score',
          'why_relevant', 'deadline_alert', 'filter', 'source_url', 'source_hash',
          'source_changed', 'verification_note', 'discovered_via']


def csv_text(records):
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=FIELDS, extrasaction='ignore')
    writer.writeheader()
    for r in records:
        row = {k: json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v for k, v in r.items()}
        # Spreadsheet formula injection prevention for discovered titles/descriptions.
        row = {k: "'" + str(v) if isinstance(v, str) and v.startswith(('=', '+', '-', '@')) else v for k, v in row.items()}
        writer.writerow(row)
    return buf.getvalue()


def safe(s):
    return str(s or '').replace('\n', ' ').replace('[', '\\[').replace(']', '\\]').replace('<', '&lt;').replace('>', '&gt;')


def link(label, url):
    if not url or not url.startswith(('https://', 'http://')):
        return safe(label)
    return f'[{safe(label)}](<{url.replace(chr(62), "%3E")}>)'


def render(records, new, updated, now, errors, mode):
    included = [r for r in records if r['filter'] != 'excluded']
    included.sort(key=lambda r: (-r['relevance_score'], r['name']))
    lines = ['# Mathematical Modelling Competition Monitor', '',
             f"Generated: {now.astimezone(HK).isoformat()} (Asia/Hong_Kong)", '',
             f'**Mode: {mode}.** Dates and eligibility require current official confirmation before payment or registration.', '',
             f"{len(included)} opportunities / leads; {sum(r['id'] in new for r in included)} new opportunities / leads; {len(updated)} changed records; "
             f"{sum(bool(r['deadline_alert']) for r in included)} actionable deadlines within 30 days.", '',
             'Scores measure interest fit, not organizer quality or confirmed eligibility. Missing information remains unknown.', '']
    groups = [
        ('A. Newly discovered opportunities', [r for r in included if r['id'] in new]),
        ('B. Currently open competitions', [r for r in included if r['status'] == 'open']),
        ('C. Approaching registration deadlines', sorted([r for r in included if r['deadline_alert']], key=lambda r: r['deadline'])),
        ('D. Announced future competitions', [r for r in included if r['status'] in ('announced', 'not_yet_open')]),
        ('E. Watch for the next edition / verify manually', [r for r in included if r['status'] in ('closed', 'unknown')]),
    ]
    for title, rows in groups:
        lines += ['## ' + title, '']
        if not rows:
            lines += ['None identified in this run.', '']
        for r in rows:
            lines += [f"### {link(r['name'], r['official_url'])} — {r['relevance_score']}/100", '',
                      f"{safe(r.get('organizer', 'Organizer unverified'))} · {safe(r.get('category', 'Discovery lead'))} · {r['status']} · {r['filter']}", '',
                      safe(r.get('description', '')), '',
                      f"**Why it fits:** {safe(r.get('why_relevant', 'Pending review.'))}", '',
                      f"**Eligibility / team:** {safe(r.get('eligibility', 'Unverified'))} / {safe(r.get('team_size') or 'Unknown')}. Format: {safe(r.get('format', 'unknown'))}.", '',
                      f"**Registration deadline:** {safe(r.get('deadline_original') or 'Unknown; not inferred')} "
                      f"({safe(r.get('deadline_timezone') or 'time zone unknown')}); **Hong Kong:** {safe(r.get('deadline_hkt') or 'Unknown')}. "
                      f"{safe(r.get('deadline_alert', ''))}", '',
                      f"**Competition dates:** {safe(r.get('competition_dates') or 'Unknown')}. "
                      f"**Fees:** {safe(r.get('fees') or 'Unknown')}. **Prizes:** {safe(r.get('prizes') or 'Unknown')}.", '',
                      f"{link('Official evidence', r.get('source_url', r['official_url']))} · "
                      f"{link('Registration', r.get('registration_url', ''))} · "
                      f"Last verified: {safe(r.get('last_verified') or 'Never')} · {safe(r.get('verification'))}", '',
                      safe(r.get('verification_note', '')), '']
    lines += ['## Changes requiring attention', '']
    names = {r['id']: r['name'] for r in records}
    lines += [f"- {safe(names[c['id']])}: {', '.join(c['fields'])}" for c in updated] or ['No changed tracked fields.']
    lines += ['', '## Source health', '']
    lines += [f'- {safe(e)}' for e in errors] or ['No recorded fetch errors.']
    lines += ['', '## Exclusions', '']
    lines += [f"- {safe(r['name'])}: {safe(r.get('excluded_reason', 'Not eligible / insufficient mathematical modelling'))}" for r in records if r['filter'] == 'excluded']
    return '\n'.join(lines) + '\n'
