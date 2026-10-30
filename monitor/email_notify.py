"""Opt-in SMTP over TLS. Nothing is sent without explicit environment settings."""
import argparse
from email.message import EmailMessage
import os
from pathlib import Path
import smtplib
import ssl
from .core import atomic_json, load_json, now_utc
from .macos import plan


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data', type=Path, default=Path('data'))
    args = p.parse_args()
    required = ['SMTP_HOST', 'SMTP_USER', 'SMTP_PASSWORD', 'SMTP_FROM', 'SMTP_TO']
    if not all(os.environ.get(k) for k in required):
        print('Email disabled: all five SMTP settings must be supplied.')
        return
    path = args.data / 'email-state.json'
    state = load_json(path, {'schema_version': 1, 'delivered': []})
    manifest = load_json(args.data / 'updates.json')
    events = plan(manifest, state, now_utc())
    high_ids = {'run:' + r['id'] for r in manifest['runs'] if r.get('high_relevance')}
    for event in events:
        if not (event['key'].startswith('deadline:') or event['key'] in high_ids):
            continue
        message = EmailMessage()
        message['Subject'] = event['title']
        message['From'] = os.environ['SMTP_FROM']
        message['To'] = os.environ['SMTP_TO']
        message.set_content(event['message'] + '\n\n' + (event.get('url') or 'See data/report.md'))
        with smtplib.SMTP_SSL(os.environ['SMTP_HOST'], int(os.environ.get('SMTP_PORT', '465')),
                              timeout=20, context=ssl.create_default_context()) as smtp:
            smtp.login(os.environ['SMTP_USER'], os.environ['SMTP_PASSWORD'])
            smtp.send_message(message)
        state['delivered'].append(event['key'])
        atomic_json(path, state)


if __name__ == '__main__':
    main()
