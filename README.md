# Mathematical Modelling Competition Monitor

A Python 3.9+ monitor for an HKUST mathematics/finance undergraduate. No pip packages, LLM API, database server or continuously running process is required. Python must have IANA time-zone data (standard on macOS and GitHub's Ubuntu runners).

## Quick start

Run these commands from this project folder:

```sh
python3 -m unittest discover -s tests -v
python3 -m monitor.scan --offline --output work/demo --as-of 2026-10-30T09:00:00+08:00
open work/demo/report.md
python3 -m monitor.scan
open data/report.md
```

The first scan is an explicitly labelled, reproducible **research baseline**, not a live scrape. The second scan makes bounded live HTTP requests and discovers additional leads. Real source failures are listed in the report. Do not publish `work/demo` as production history. The supplied [sample report](examples/report.md) and [competitions.csv](examples/competitions.csv) were generated from official-source research on 30 October 2026. No example deadline was invented. The separate notification demo uses **synthetic fixtures**.

## Architecture and source strategy

`monitor/sources.py` fetches official pages, respects robots.txt, throttles each host, retries transient failures once, caps page sizes and uses finite timeouts. Official HTML link directories and configurable RSS/Atom feeds discover organizations outside the initial catalog. `config/sources.json` includes English and Chinese sources and eight global search queries. Only HTTP(S) is fetched. Search is an optional legitimate Brave API adapter, never Google result scraping. No LLM is involved.

`config/catalog.json` holds reviewed structured facts, official evidence URLs and short evidence markers. `monitor/core.py` applies HKUST eligibility, deterministic interest scores, deduplication and date/status rules. `monitor/scan.py` preserves records, writes full historical snapshots and computes changes. `monitor/report.py` produces readable Markdown and spreadsheet-safe CSV. `monitor/macos.py` consumes the completion manifest without rerunning discovery; `monitor/notifier.py` is a replaceable native-delivery adapter. The notification extension depends only on the versioned JSON contract, so it can be attached to another existing pipeline by publishing the same manifest.

The no-key tier finds links from the configured official/society sites, including external new organizers. It cannot search the entire web or guarantee completeness. Add more official hubs/RSS URLs for broader free coverage. Optional search expands discovery to unknown organizers globally, in both languages. Discovery leads are **unverified**, not promises of admission or deadlines. A high-school-only event is excluded only when its rules are established, rather than from a misleading snippet containing “high school.” Clearly ineligible events remain in CSV for audit but are omitted from opportunity sections.

## Data and verification

Each CSV row has organizer, URLs, category, edition, description, possible techniques, eligibility/team/format, original deadline, explicit time zone, offset-aware ISO deadline, Hong Kong conversion, contest dates, fees, prizes, status, verification dates, relevance and reasons. Blank fields mean unknown. Potential modelling techniques are suggestions, not claims about unpublished problems.

Statuses: `open`, `announced`, `not_yet_open`, `closed`, `unknown`. Only a verified eligible record explicitly marked open is actionable. A missing deadline never implies closed or supplies an invented end-of-day time. Deadlines with unknown times/zones remain textual evidence, with no computed reminder. Offset-aware ISO dates and explicit IANA zones are supported; naive, ambiguous DST and nonexistent wall-clock times are rejected. Original time-zone labels are preserved. EuroMCM literally prints CET in October: the sample preserves UTC+01:00 and flags that organizer clarification is advisable, rather than silently changing to summer time. CUMCM's international English-site registration deadline/fee waiver is **not applied to Hong Kong students**, who are directed to a different process.

The baseline includes COMAP, EuroMCM, CUMCM, INFORMS, Rotman, IISE and a SCUDEM lead from SIAM. Some records are paused, historical or require manual eligibility checks. Closed annual competitions remain in the next-edition watchlist; future dates are not extrapolated.

**Conservative verification is intentional.** The MVP does not infer arbitrary prose into confirmed new dates. Evidence markers must still match, and any normalized official-page text change after the first live fetch sets `needs_review` and suppresses actionable alerts. A fetch failure sets `unavailable`, preserving prior facts and last successful verification date. An unchanged page does not prove the organizer's own content is current. New editions and changed restrictions require a small catalog edit. This can create false-positive review work when unrelated page text changes; it avoids silently relying on stale rules.

To review an event:

1. Follow `source_url` and current registration/rules links. Confirm the edition, HKUST eligibility, travel, fees and exact dates.
2. Edit its catalog facts and critical evidence markers, set `verification` to `verified`, and update `last_verified`. Use the same stable `series_id` for annual editions. Update both `official_url` and `registration_url` when appropriate. Add a new edition only when officially announced.
3. For a previously detected page change, copy the inspected current `source_hash` from `data/state.json` into `reviewed_source_hash` in that catalog entry. Do not copy a hash without reviewing the source. If the page changed again, another review is required.
4. Run the scanner and inspect the report. To explicitly retire an event, set `excluded_reason`; absence from a feed never deletes historical records.

URL deduplication removes trackers/fragments and normalizes www/trailing slashes, while keeping query IDs. Stable series IDs and identical official URLs merge listings. Aliases on entirely different domains cannot reliably be inferred: when promoting a lead, preserve its ID as `series_id` or use its same canonical URL. Different title spellings alone are never used to merge unrelated contests.

Scores are deterministic sums: modelling 35, optimization 20, probability 15, finance 15, data 10, interdisciplinary 5; undergraduate suitability +10 and online +5, capped at 100. They indicate interest fit, not legitimacy. High relevance means >=80 **and verified/actionable** for notification highlights. New unverified leads are still visible in the report.

## GitHub Actions deployment — no Mac required for scanning

1. Create a GitHub repository and copy **this folder's contents**, including `.github`, into its root. Keep source code on the repository's default branch, normally `main`. The simplest no-secret setup uses a public repository. Avoid publishing personal information in catalog/history.
2. Push the project (replace the example owner/repository):

   ```sh
   git init -b main
   git add .
   git commit -m 'Add competition monitor and macOS notifications'
   git remote add origin https://github.com/YOUR_NAME/YOUR_REPO.git
   git push -u origin main
   ```

3. In GitHub **Settings → Actions → General**, allow Actions and workflow read/write contents permissions if your organization permits them. The workflow declares `contents: write`. The separate generated `monitor-data` branch must permit this bot to push; source-branch protection can remain enabled.
4. In **Actions → Weekly Competition Monitor → Run workflow**, run once manually on the default branch. Tests run before the live scan. The first successful publish creates `monitor-data`, containing `data/report.md`, `data/competitions.csv`, `data/state.json`, `data/history/*.json`, and `data/updates.json`. Open those files on that branch.
5. The included cron, `0 1 * * 1` UTC, targets **Monday 09:00 Asia/Hong_Kong**. Hong Kong has no daylight saving time. GitHub scheduling is best effort: starts can be delayed or dropped; manual dispatch remains available. Public scheduled workflows can be disabled after 60 days without repository activity. See [GitHub's schedule documentation](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).

Historical state is restored from `monitor-data` before each scan. All results are published in one commit after the scan and optional email step. Concurrency prevents overlapping scheduled/manual scans from overwriting history. A scan completion means the scan finished, even with reported source errors; it does not mean every source was available. A failed scan/test/publish produces no new externally visible completion manifest. The weekly run ID is stable across retries of that GitHub Actions run. Notification counters exclude known ineligible records.

The data branch is independent of the source branch, keeping generated output out of source commits. Completion history has no artificial short retention limit, so a Mac can catch up after a long shutdown. Full snapshots and history will grow; at weekly cadence and a small catalog this is modest. Review storage after substantial expansion. The local manifest reader caps input at 5 MB, and reports an error rather than silently losing state if this is exceeded.

## macOS native notifications

The weekly scan stays in GitHub. A per-user **LaunchAgent** starts a short Python check after login and hourly while you are logged in. It makes one GitHub Contents API request, exits, and does no scraping. launchd does not wake a powered-off Mac; the persistent manifest is checked at the next login. Network failures are retried on the next scheduled invocation. Checks do not keep a Python daemon running or require a Mac-hosted GitHub runner.

### Install

Python 3.9+ must be installed at a stable location (python.org or Homebrew is suitable). Run from the project root after the first successful cloud scan:

```sh
sh scripts/install-macos.sh --repo YOUR_NAME/YOUR_REPO
```

The installer copies runtime modules into `~/Library/Application Support/MathModellingMonitor/runtime` and writes `~/Library/LaunchAgents/org.mathmodelling.monitor.plist`. It captures the absolute Python executable and notifier path, supports spaces in paths, uses the logged-in GUI session and requires no sudo. Re-run after updating the project or relocating Python. This installs one monitored repository per user; reinstallation preserves previously delivered IDs. Use `--interval 7200` for two-hour checks (minimum 900 seconds).

Preview the exact files without installing or sending notifications:

```sh
sh scripts/install-macos.sh --repo YOUR_NAME/YOUR_REPO --preview-dir work/install-preview
plutil -lint work/install-preview/LaunchAgents/org.mathmodelling.monitor.plist
```

### Delivery, permissions and click-to-open

By default the checker uses standard macOS AppleScript `display notification`. On first delivery, macOS registers the script/runtime as a notification sender. In **System Settings → Notifications**, enable notifications for the sender that appears (often Script Editor or osascript; attribution varies by macOS). Check Focus and notification summaries if banners do not appear. A successful osascript return means the request was submitted; it cannot prove you saw a banner or that macOS permitted it.

The AppleScript API does not offer a custom report-click URL. For reliable clickable report links, install the optional free open-source [terminal-notifier](https://github.com/julienXX/terminal-notifier), then rerun the installer so it captures its path:

```sh
brew install terminal-notifier
sh scripts/install-macos.sh --repo YOUR_NAME/YOUR_REPO
```

Allow **terminal-notifier** in System Settings → Notifications and choose Banners or Alerts. Its `-open` action opens the latest GitHub Markdown report when clicked. You can instead supply `--report-url file:///absolute/path/report.md` to manual checker commands; the local file must exist and be kept updated separately. No third-party messaging service is required. The checker uses noninteractive delivery, so it exits immediately rather than waiting for clicks. [Apple notification API behavior](https://developer.apple.com/library/archive/documentation/LanguagesUtilities/Conceptual/MacAutomationScriptingGuide/DisplayNotifications.html) and [terminal-notifier options](https://github.com/julienXX/terminal-notifier#options) describe platform limitations.

Test native delivery once in a logged-in Terminal (bypasses production alert state):

```sh
python3 -c 'from monitor.notifier import deliver; deliver({"title":"Math Modelling Monitor — Test","message":"Native notifications are working.","key":"monitor-test","url":"https://github.com/YOUR_NAME/YOUR_REPO/blob/monitor-data/data/report.md"})'
```

Grant permission and repeat this test before relying on unattended delivery. Native banners/clicks must be checked on your own macOS GUI session. Unit tests mock the OS submission call; they cannot validate user-visible OS permissions.

### Alert rules and deduplication

- Every completed weekly scan triggers a summary, including zero-result weeks. Manual live scans also produce summaries, labelled Update. Source errors are mentioned.
- Newly discovered verified, actionable competitions scoring >=80 are highlighted by name. High-scoring but unverified leads remain report-only.
- Each distinct competition/deadline receives one extra alert upon entering the final seven days, even between weekly scans. Revised deadlines receive a new alert. Expired, uncertain and older-than-14-day snapshot deadlines do not trigger urgent alerts.
- Missed summaries are replayed once each after login, with their original weekly counts. Old urgent alerts are recalculated against the latest snapshot and current time, rather than replayed after expiry. Initial installation replays all saved production completions, which may produce several notifications if the project has a long history.
- Delivered run IDs and competition/deadline pairs are stored per repository in the local state folder. Offline research runs are not notified. Dry runs never send or acknowledge.
- A file lock serializes local checks. State is saved atomically after each successful submission. Failed commands are retried next check. A crash between OS submission and state persistence has a small duplicate window; true exactly-once visible OS delivery is unavailable. `terminal-notifier` uses a deterministic group to replace duplicates in that window. AppleScript has no group support.

Manual read-only notification preview:

```sh
python3 -m monitor.macos --repo YOUR_NAME/YOUR_REPO --dry-run
```

Mock demo (synthetic competitions/deadlines, no network):

```sh
python3 scripts/demo-notifications.py
```

The demo prints a weekly summary, a high-relevance highlight and a 7-day alert, simulates successful delivery into an isolated temporary state file, then asserts the second check generates **zero** duplicates. It does not display real notifications or change production state.

### Disable, re-enable and troubleshoot

```sh
sh scripts/uninstall-macos.sh
# Re-enable later; delivery state is preserved:
sh scripts/install-macos.sh --repo YOUR_NAME/YOUR_REPO
# Inspect the loaded service:
launchctl print gui/$(id -u)/org.mathmodelling.monitor
```

Logs are `~/Library/Application Support/MathModellingMonitor/checker.log` and `checker-errors.log`. Normal checks are silent. If network/credentials fail persistently, inspect and clear old logs periodically. To retry a notification deliberately, back up the appropriate `seen-*.json` file and remove only its key. Removing that whole file replays all completions. Uninstall removes only the LaunchAgent; you can remove the application-support folder yourself to erase runtime and state. GitHub scanning remains independent.

## Secrets, services and costs

The initial MVP requires **no credentials or paid API** for local scans or public-repository Mac checks. Python and native macOS notifications are free. A public repository lets anyone read competition results. GitHub-hosted standard runners on public repositories are generally free; private repositories consume the account's included allowance and may incur charges. This workflow normally runs weekly; runner pricing/limits are account dependent: [GitHub Actions billing](https://docs.github.com/en/billing/managing-billing-for-your-products/managing-billing-for-github-actions/about-billing-for-github-actions).

Optional global search: create a Brave Search API account and set `BRAVE_SEARCH_API_KEY` as a GitHub Actions repository secret or an environment variable for local scans. It makes at most eight search requests per scan (plus at most one retry per failed request), roughly 32–40/month before retries/manual runs. As checked 30 October 2026, [Brave Search pricing](https://api-dashboard.search.brave.com/documentation/pricing) lists $5/1,000 search requests with $5 monthly credits; billing/enrollment terms can change. Check the provider before enabling. No key means no Brave requests and no Brave charges. Search snippets are never authoritative evidence.

Optional private repository: set `MONITOR_GITHUB_TOKEN` for manual Mac checks to a fine-grained token scoped to that repository with **Contents: read**. Do not place a token in the repository URL or source files. The no-secret LaunchAgent installer targets public repositories. Private unattended use needs a separate secure token provisioner (for example a Keychain-backed wrapper); this MVP intentionally does not persist tokens in plist files. Do not assume a token exported in Terminal will be inherited by launchd.

Optional email: use SMTP with implicit TLS, typically port 465. Set Actions secrets `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_TO`. A provider-issued app password may be required. For local manual use, set those environment variables and run:

```sh
python3 -m monitor.email_notify --data data
```

No settings means no email. SMTP port can be overridden locally with `SMTP_PORT`. No paid email provider is required, but provider quotas/pricing and authentication policies apply. Emails are sent for new actionable high-relevance competitions and 7-day deadlines, with a separate persisted delivery state. Email failure is non-blocking for the scan workflow; inspect the email step and retry manually if needed. Email has the same send-before-state duplicate window and cannot guarantee delivery or exactly-once behavior after a runner is lost.

## Tests and limitations

```sh
python3 -m unittest discover -s tests -v
```

Tests cover profile filtering, time-zone conversion/DST rejection, duplicate URLs and series IDs, meaningful field changes, failures and robots exclusions, English/Chinese HTML/RSS discovery, official-page drift, sequential scans/history, zero-result summaries, offline/mock isolation, missed updates, threshold crossing between scans, expired/stale suppression, failed-delivery retries, notification command escaping, clickable backend selection and LaunchAgent plists. `scripts/demo-notifications.py` exercises the entire manifest-to-state notification path with a mock sender. No real email or OS notification is sent by tests.

New arbitrary prose dates and eligibility rules require human verification. This is deliberately a verifiable monitoring/review pipeline rather than an autonomous registration assistant. GitHub outages, website redesigns and macOS notification settings remain external dependencies. No cloud notification can appear on a Mac that is powered off or has no logged-in GUI session; the next local check catches up.
