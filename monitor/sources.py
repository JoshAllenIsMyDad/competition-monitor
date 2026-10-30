"""Bounded official-site discovery, RSS/Atom, optional legitimate search API."""
import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.request
import urllib.robotparser
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, urlencode
from .core import canonical_url

USER_AGENT = 'MathCompetitionMonitor/1.0 (weekly academic opportunity monitor)'
MAX_BYTES = 2_000_000
TERMS = re.compile(r'modell?ing|optimization|operations research|quantitative|数学建模|數學建模|運籌|运筹', re.I)
CONTEST = re.compile(r'competition|contest|challenge|竞赛|競賽|大赛|大賽', re.I)


class Page(HTMLParser):
    def __init__(self, body):
        super().__init__(convert_charrefs=True)
        self.texts, self.links, self.href, self.label = [], [], None, []
        self.hidden = 0
        self.feed(body)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ('script', 'style'):
            self.hidden += 1
        if tag == 'a':
            self.href, self.label = attrs.get('href'), []

    def handle_endtag(self, tag):
        if tag in ('script', 'style'):
            self.hidden = max(0, self.hidden - 1)
        if tag == 'a' and self.href:
            self.links.append((self.href, ' '.join(self.label)))
            self.href = None

    def handle_data(self, data):
        if not self.hidden:
            self.texts.append(data)
            if self.href:
                self.label.append(data)

    @property
    def text(self):
        return ' '.join(' '.join(self.texts).split())


class Fetcher:
    def __init__(self):
        self.robots, self.last, self.cache = {}, {}, {}
        self.errors = []

    def _request(self, url, headers=None):
        if urlsplit(url).scheme not in ('http', 'https'):
            raise ValueError('Only HTTP(S) source URLs supported')
        request = urllib.request.Request(url, headers={'User-Agent': USER_AGENT, **(headers or {})})
        for attempt in range(2):
            try:
                with urllib.request.urlopen(request, timeout=15) as response:
                    body = response.read(MAX_BYTES + 1)
                    if len(body) > MAX_BYTES:
                        raise ValueError('Source exceeds 2 MB limit')
                    return body.decode(response.headers.get_content_charset() or 'utf-8', errors='replace')
            except urllib.error.HTTPError as error:
                if error.code not in (429, 500, 502, 503, 504) or attempt:
                    raise
                time.sleep(1)
            except (OSError, TimeoutError):
                if attempt:
                    raise
                time.sleep(1)

    def get(self, url, robots=True):
        if url in self.cache:
            return self.cache[url]
        p = urlsplit(url)
        origin = f'{p.scheme}://{p.netloc}'
        if robots:
            if origin not in self.robots:
                rp = urllib.robotparser.RobotFileParser()
                try:
                    rp.parse(self._request(origin + '/robots.txt').splitlines())
                except urllib.error.HTTPError as e:
                    if e.code == 404:
                        rp.parse([])
                    else:
                        raise ValueError('robots.txt unavailable; skipping host') from e
                self.robots[origin] = rp
            rp = self.robots[origin]
            if not rp.can_fetch(USER_AGENT, url):
                raise ValueError('robots.txt disallows this URL')
            delay = max(1, rp.crawl_delay(USER_AGENT) or rp.crawl_delay('*') or 1)
            time.sleep(max(0, delay - (time.monotonic() - self.last.get(origin, 0))))
        try:
            body = self._request(url)
            self.cache[url] = body
            return body
        finally:
            self.last[origin] = time.monotonic()


def candidate(title, url, via):
    return {'name': title[:200], 'official_url': url, 'discovered_via': via,
            'eligibility_state': 'unclear', 'verification': 'unverified',
            'registration_state': 'unknown', 'description': 'Discovery lead; official organizer, dates and eligibility require review.',
            'tags': ['modelling'], 'why_relevant': 'Keyword match; mathematical depth and HKUST access need verification.'}


def discover(config, fetcher):
    found = []
    for source in config.get('discovery_sources', []):
        try:
            body = fetcher.get(source['url'])
            if source.get('type') == 'rss':
                root = ET.fromstring(body)
                links = []
                for item in list(root.findall('.//item')) + list(root.findall('.//{http://www.w3.org/2005/Atom}entry')):
                    title = item.findtext('title') or item.findtext('{http://www.w3.org/2005/Atom}title') or ''
                    link = item.find('link')
                    if link is None:
                        link = item.find('{http://www.w3.org/2005/Atom}link')
                    if link is not None:
                        links.append((link.get('href') or link.text or '', title))
            else:
                links = Page(body).links
            for href, title in links:
                if TERMS.search(title) and CONTEST.search(title):
                    url = urljoin(source['url'], href)
                    if urlsplit(url).scheme in ('http', 'https'):
                        found.append(candidate(title, url, source['url']))
        except Exception as e:
            fetcher.errors.append(f"Discovery {source['url']}: {type(e).__name__}: {e}")
    key = os.environ.get('BRAVE_SEARCH_API_KEY')
    if key:
        for query in config.get('queries', [])[:8]:
            try:
                url = 'https://api.search.brave.com/res/v1/web/search?' + urlencode({'q': query, 'count': 10})
                results = json.loads(fetcher._request(url, {'X-Subscription-Token': key}))
                for item in results.get('web', {}).get('results', []):
                    title, url = item['title'], item['url']
                    if TERMS.search(title + ' ' + item.get('description', '')) and CONTEST.search(title):
                        found.append(candidate(title, url, 'Brave: ' + query))
                time.sleep(1)
            except Exception as e:
                # Do not echo request headers, tokens, or response bodies.
                fetcher.errors.append(f'Brave query failed: {type(e).__name__}')
    return found


def verify(record, fetcher, now, previous=None):
    r = dict(record)
    for k in ('source_hash', 'source_changed', 'last_fetched'):
        if previous and k in previous:
            r[k] = previous[k]
    if not r.get('source_url'):
        return r
    try:
        text = Page(fetcher.get(r['source_url'])).text
        digest = hashlib.sha256(text.encode()).hexdigest()
        r['last_fetched'] = now.isoformat()
        changed = bool(previous and previous.get('source_hash') and previous['source_hash'] != digest)
        r['source_hash'] = digest
        # Page changes are deliberately conservative: human review prevents a changed
        # restriction elsewhere on the page from silently passing stale eligibility.
        r['source_changed'] = bool(changed or r.get('source_changed', False))
        anchors = r.get('evidence_markers', [])
        if not anchors or not all(a.casefold() in text.casefold() for a in anchors) or r['source_changed']:
            r['verification'] = 'needs_review'
            r['verification_note'] = 'Official page changed or evidence no longer matches. Review config/catalog.json; do not infer next edition.'
        else:
            r['verification'] = record.get('verification', 'unverified')
            if r['verification'] == 'verified':
                r['last_verified'] = now.isoformat()
        # Curator can acknowledge an inspected page using its hash in the catalog.
        if record.get('reviewed_source_hash') == digest and anchors and all(a.casefold() in text.casefold() for a in anchors):
            r['source_changed'] = False
            r['verification'] = record['verification']
            r['last_verified'] = now.isoformat()
    except Exception as e:
        r['verification'] = 'unavailable'
        r['verification_note'] = f'Official source unavailable: {type(e).__name__}. Historical facts retained.'
        if previous:
            r['last_verified'] = previous.get('last_verified', r.get('last_verified', ''))
        fetcher.errors.append(f"Verification {r['source_url']}: {type(e).__name__}: {e}")
    return r
