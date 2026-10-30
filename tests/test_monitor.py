from datetime import timedelta
import json
import contextlib
import io
from pathlib import Path
import plistlib
import tempfile
import unittest
from unittest.mock import patch, Mock
from zoneinfo import ZoneInfo
from monitor.core import changes, decorate, deduplicate, filter_record, parse_date
from monitor.install_macos import launchagent
from monitor.macos import plan, process, validate_manifest, fetch_manifest
from monitor.notifier import command, deliver
from monitor.report import csv_text
from monitor.scan import run
from monitor.sources import Fetcher, Page, discover, verify

NOW = parse_date('2026-10-30T09:00:00+08:00')
ROOT = Path(__file__).resolve().parents[1]


def competition(**kw):
    return dict({'id': 'sample', 'series_id': 'sample', 'name': 'Sample',
                 'official_url': 'https://example.org/contest',
                 'eligibility_state': 'eligible', 'verification': 'verified',
                 'registration_state': 'open', 'deadline': '2026-11-04T12:00:00+08:00'}, **kw)


def manifest(**kw):
    value = {'schema_version': 1, 'generated_at': NOW.isoformat(),
             'report_url': 'https://github.com/example/repo/blob/monitor-data/data/report.md',
             'runs': [{'id': 'weekly-1', 'kind': 'weekly', 'completed_at': NOW.isoformat(),
                       'new': 0, 'updated': 0, 'upcoming': 1, 'high_relevance': []}],
             'competitions': [decorate(competition(), NOW)]}
    value.update(kw)
    return value


class DatesAndFiltering(unittest.TestCase):
    def test_est_to_hong_kong(self):
        dt = parse_date('2027-01-28T15:00:00-05:00')
        self.assertEqual(dt.astimezone(ZoneInfo('Asia/Hong_Kong')).isoformat(), '2027-01-29T04:00:00+08:00')

    def test_unknown_date_only_naive_and_explicit_zone(self):
        self.assertIsNone(parse_date(''))
        self.assertIsNone(parse_date('2026-11-04'))
        with self.assertRaises(ValueError):
            parse_date('2026-11-04T09:00:00')
        self.assertEqual(parse_date('2026-11-04T09:00:00', 'Asia/Hong_Kong').utcoffset(), timedelta(hours=8))

    def test_dst_ambiguity_and_nonexistent_times(self):
        for value in ['2026-11-01T01:30:00', '2026-03-08T02:30:00']:
            with self.assertRaises(ValueError):
                parse_date(value, 'America/New_York')

    def test_eligibility_exclusions_and_manual(self):
        for fields in [{'level': 'high_school_only'}, {'meaningful_modelling': False},
                       {'eligibility_state': 'ineligible'}, {'excluded_reason': 'country restricted'}]:
            self.assertEqual(filter_record(competition(**fields)), 'excluded')
        self.assertEqual(filter_record(competition(eligibility_state='unclear')), 'manual_verification')
        self.assertEqual(filter_record(competition()), 'eligible')

    def test_statuses_and_deadline_boundaries(self):
        for days, expected in [(7, '7 days'), (30, '30 days'), (31, ''), (-1, '')]:
            r = decorate(competition(deadline=(NOW + timedelta(days=days)).isoformat()), NOW)
            self.assertEqual(r['deadline_alert'], expected)
            if days < 0:
                self.assertEqual(r['status'], 'closed')
        self.assertEqual(decorate(competition(verification='needs_review'), NOW)['status'], 'unknown')
        self.assertFalse(decorate(competition(eligibility_state='unclear'), NOW)['actionable'])
        for state in ['announced', 'not_yet_open', 'unknown']:
            self.assertEqual(decorate(competition(registration_state=state), NOW)['status'], state)

    def test_dedupe_urls_series_and_query_identity(self):
        a = competition()
        b = competition(official_url='http://www.example.org/contest/?utm_source=foo#top')
        self.assertEqual(len(deduplicate([a, b])), 1)
        b['official_url'] = 'https://new.example.org/2027'
        self.assertEqual(len(deduplicate([a, b])), 1)
        self.assertEqual(len(deduplicate([{'official_url': 'https://example.org/?id=1'},
                                         {'official_url': 'https://example.org/?id=2'}])), 2)

    def test_change_detection(self):
        old = competition(last_verified='old')
        self.assertEqual(changes([old], [competition(last_verified='new')]), ([], []))
        new, updated = changes([old], [competition(deadline='2026-11-05T12:00:00+08:00')])
        self.assertEqual(new, [])
        self.assertEqual(updated[0]['fields'], ['deadline'])
        self.assertEqual(changes([], [old])[0], ['sample'])


class Sources(unittest.TestCase):
    def test_unavailable_preserves_history(self):
        f = Mock(errors=[])
        f.get.side_effect = OSError('offline')
        r = verify(competition(source_url='https://example.org/'), f, NOW, competition(last_verified='2026-10-20'))
        self.assertEqual(r['verification'], 'unavailable')
        self.assertEqual(r['last_verified'], '2026-10-20')
        self.assertEqual(r['deadline'], competition()['deadline'])

    def test_changed_page_and_acknowledgement(self):
        f = Mock(errors=[])
        f.get.return_value = '<p>Undergraduates 2027</p>'
        r = competition(source_url='https://example.org/', evidence_markers=['Undergraduates', '2027'])
        verified = verify(r, f, NOW)
        self.assertEqual(verified['verification'], 'verified')
        f.get.return_value = '<p>Undergraduates 2027. Only domestic residents.</p>'
        changed = verify(r, f, NOW, verified)
        self.assertTrue(changed['source_changed'])
        self.assertEqual(changed['verification'], 'needs_review')
        self.assertEqual(verify(r, f, NOW, changed)['verification'], 'needs_review')
        r['reviewed_source_hash'] = changed['source_hash']
        self.assertEqual(verify(r, f, NOW, changed)['verification'], 'verified')

    def test_html_rss_discover_unknown_organizers(self):
        f = Mock(errors=[])
        f.get.side_effect = [
            '<a href="https://new.example/contest">New quantitative modelling competition</a>',
            '<rss><channel><item><title>新数学建模竞赛</title><link>https://another.example/new</link></item></channel></rss>']
        with patch.dict('os.environ', {'BRAVE_SEARCH_API_KEY': ''}):
            found = discover({'discovery_sources': [{'url': 'https://hub.example/'}, {'url': 'https://hub.example/feed', 'type': 'rss'}]}, f)
        self.assertEqual(len(found), 2)
        self.assertTrue(all(r['eligibility_state'] == 'unclear' for r in found))

    def test_failed_feed_continues(self):
        f = Mock(errors=[])
        f.get.side_effect = OSError('unavailable')
        with patch.dict('os.environ', {'BRAVE_SEARCH_API_KEY': ''}):
            self.assertEqual(discover({'discovery_sources': [{'url': 'https://example.org/'}]}, f), [])
        self.assertEqual(len(f.errors), 1)

    def test_html_drops_scripts(self):
        self.assertEqual(Page('<script>registration open</script><p>Closed</p>').text, 'Closed')

    def test_robots_disallow(self):
        f = Fetcher()
        f._request = Mock(return_value='User-agent: *\nDisallow: /')
        with self.assertRaises(ValueError):
            f.get('https://example.org/private')
        self.assertEqual(f._request.call_count, 1)


class Notifications(unittest.TestCase):
    def test_zero_result_week_and_extra_urgent_alert(self):
        events = plan(manifest(), {}, NOW)
        self.assertEqual(len(events), 2)
        self.assertIn('0 new competitions, 0 updated', events[0]['message'])
        self.assertIn('Weekly Update', events[0]['title'])
        self.assertIn('7 days', events[1]['title'])

    def test_unchanged_results_no_repeat_changed_deadline_alerts(self):
        m = manifest()
        state = {'delivered': [e['key'] for e in plan(m, {}, NOW)]}
        self.assertEqual(plan(m, state, NOW), [])
        m['competitions'][0]['deadline'] = '2026-11-05T12:00:00+08:00'
        self.assertEqual(len(plan(m, state, NOW)), 1)

    def test_same_deadline_in_another_zone_not_repeated(self):
        m = manifest()
        state = {'delivered': [e['key'] for e in plan(m, {}, NOW)]}
        m['competitions'][0]['deadline'] = '2026-11-04T04:00:00+00:00'
        self.assertEqual(plan(m, state, NOW), [])

    def test_enters_seven_days_without_new_cloud_run(self):
        m = manifest()
        m['competitions'][0]['deadline'] = (NOW + timedelta(days=9)).isoformat()
        state = {'delivered': ['run:weekly-1']}
        self.assertEqual(plan(m, state, NOW), [])
        self.assertEqual(len(plan(m, state, NOW + timedelta(days=3))), 1)

    def test_missed_updates_and_stale_suppression(self):
        m = manifest()
        m['runs'].append(dict(m['runs'][0], id='weekly-2'))
        self.assertEqual([e['key'] for e in plan(m, {}, NOW + timedelta(days=20))], ['run:weekly-1', 'run:weekly-2'])

    def test_expired_and_unverified_no_urgent_alert(self):
        for fields in [{'actionable': False}, {'deadline': (NOW - timedelta(seconds=1)).isoformat()}]:
            m = manifest()
            m['competitions'][0].update(fields)
            self.assertEqual(len(plan(m, {}, NOW)), 1)

    def test_offline_runs_never_notify(self):
        m = manifest(offline=True)
        m['runs'][0]['offline'] = True
        self.assertEqual(plan(m, {}, NOW), [])

    def test_high_relevance_and_source_errors(self):
        m = manifest(competitions=[])
        m['runs'][0].update(high_relevance=['New optimization contest'], source_errors=2)
        event = plan(m, {}, NOW)[0]
        self.assertIn('High relevance: New optimization contest', event['message'])
        self.assertIn('2 source errors', event['message'])

    def test_persist_success_and_retry_failed_delivery(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'state.json'
            sender = Mock(side_effect=[None, RuntimeError('not authorized')])
            with self.assertRaises(RuntimeError):
                process(manifest(), path, NOW, sender)
            self.assertEqual(json.loads(path.read_text())['delivered'], ['run:weekly-1'])
            sender = Mock()
            self.assertEqual(len(process(manifest(), path, NOW, sender)), 1)
            self.assertEqual(process(manifest(), path, NOW, sender), [])

    def test_dry_run_no_writes(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'state.json'
            sender = Mock()
            with contextlib.redirect_stdout(io.StringIO()):
                process(manifest(), path, NOW, sender, dry_run=True)
            sender.assert_not_called()
            self.assertFalse(path.exists())

    def test_osascript_no_code_interpolation(self):
        evil = '" & do shell script "bad"'
        args = command('Title', evil, None, 'id', 'osascript')
        self.assertEqual(args[-1], evil)
        self.assertNotIn(evil, args[2])

    def test_clickable_backend_safe_urls(self):
        with patch('shutil.which', return_value='/opt/homebrew/bin/terminal-notifier'):
            args = command('Title', 'Body', 'https://github.com/a/b', 'key')
            self.assertIn('-open', args)
            self.assertIn('-group', args)
            self.assertNotIn('-open', command('Title', 'Body', 'javascript:bad', 'key'))

    def test_native_sender_mock(self):
        with patch('platform.system', return_value='Darwin'), patch('subprocess.run') as runner:
            deliver({'title': 'T', 'message': 'M', 'key': 'K'}, 'osascript')
            runner.assert_called_once()
            self.assertTrue(runner.call_args.kwargs['check'])
            self.assertEqual(runner.call_args.kwargs['timeout'], 20)

    def test_malformed_manifest_rejected(self):
        m = manifest()
        m['runs'][0]['new'] = 'zero'
        with self.assertRaises(ValueError):
            validate_manifest(m)

    def test_launchagent_paths_and_login(self):
        value = launchagent('/some python/bin/python3', Path('/a folder/runtime'), Path('/a folder/state'), 'owner/repo')
        restored = plistlib.loads(plistlib.dumps(value))
        self.assertEqual(restored['ProgramArguments'][0], '/some python/bin/python3')
        self.assertEqual(restored['StartInterval'], 3600)
        self.assertTrue(restored['RunAtLoad'])
        self.assertEqual(restored['LimitLoadToSessionType'], 'Aqua')


class Integration(unittest.TestCase):
    def test_two_scans_and_idempotent_history(self):
        with tempfile.TemporaryDirectory() as d:
            output = Path(d)
            first = run(ROOT, output, NOW, offline=True, run_id='1', kind='weekly')
            second = run(ROOT, output, NOW, offline=True, run_id='2', kind='weekly')
            self.assertGreater(first['new'], 0)
            self.assertEqual(second['new'], 0)
            self.assertEqual(second['updated'], 0)
            run(ROOT, output, NOW, offline=True, run_id='2', kind='weekly')
            self.assertEqual(len(json.loads((output / 'updates.json').read_text())['runs']), 2)
            self.assertIn('2027-01-29T04:00:00+08:00', (output / 'report.md').read_text())
            self.assertEqual(len(list((output / 'history').glob('*.json'))), 2)

    def test_csv_injection(self):
        self.assertIn("'=HYPERLINK", csv_text([{'name': '=HYPERLINK("bad")'}]))


if __name__ == '__main__':
    unittest.main()
