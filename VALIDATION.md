# Validation

Validated on 30 October 2026 with Python 3.9.6.

- 34 unit/integration tests passed. Full output: [test-results.txt](examples/test-results.txt).
- Two sequential scans preserved records and history, with zero new/updated records on an unchanged second scan.
- Local Git publication test created the data branch, restored it, appended another completion and preserved its parent history. The source branch stayed unchanged.
- Notification fixture produced a weekly summary and a 7-day alert. A second invocation produced zero duplicates. [Demo output](examples/notification-demo.txt).
- LaunchAgent installation preview passed `plutil -lint`. Both install/uninstall scripts and the publication script passed shell syntax checks.
- Sample [report](examples/report.md) and [CSV](examples/competitions.csv) use an explicitly labelled offline research baseline: eight opportunities/leads and two exclusions, with official links. It is not a live local scan. Initial source research used official websites; network transport in tests is mocked.

No GitHub deployment, LaunchAgent activation, real email or native notification was performed. Native permissions and click behavior require a logged-in macOS GUI test using the README command. The project is ready for the documented repository setup and optional local installation.
