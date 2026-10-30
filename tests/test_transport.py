import io
import json
import unittest
from unittest.mock import Mock, patch
from monitor.macos import fetch_manifest
from monitor.sources import discover


class Transport(unittest.TestCase):
    def test_public_manifest_request_no_credentials(self):
        with patch('urllib.request.urlopen') as get:
            get.return_value.__enter__.return_value.read.return_value = b'{"schema_version":1}'
            result = fetch_manifest('owner/repo')
            request = get.call_args.args[0]
            self.assertEqual(result['schema_version'], 1)
            self.assertNotIn('Authorization', request.headers)
            self.assertIn('ref=monitor-data', request.full_url)
            self.assertEqual(get.call_args.kwargs['timeout'], 20)

    def test_private_token_is_header_only(self):
        with patch('urllib.request.urlopen') as get:
            get.return_value.__enter__.return_value.read.return_value = b'{}'
            fetch_manifest('owner/repo', token='mock-secret')
            request = get.call_args.args[0]
            self.assertEqual(request.headers['Authorization'], 'Bearer mock-secret')
            self.assertNotIn('mock-secret', request.full_url)

    def test_optional_search_uses_eight_queries_max(self):
        fetcher = Mock(errors=[])
        fetcher._request.return_value = json.dumps({'web': {'results': [
            {'title': 'New mathematical modelling competition', 'url': 'https://unknown.example/contest'}]}})
        with patch.dict('os.environ', {'BRAVE_SEARCH_API_KEY': 'mock-secret'}), patch('time.sleep'):
            found = discover({'queries': ['query'] * 10}, fetcher)
        self.assertEqual(fetcher._request.call_count, 8)
        self.assertEqual(len(found), 8)
        self.assertTrue(all(r['verification'] == 'unverified' for r in found))
