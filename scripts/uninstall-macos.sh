#!/bin/sh
set -eu
if [ "$(uname -s)" != Darwin ]; then
  echo 'This script requires macOS.' >&2
  exit 1
fi
agent="$HOME/Library/LaunchAgents/org.mathmodelling.monitor.plist"
/bin/launchctl bootout "gui/$(id -u)" "$agent" 2>/dev/null || true
rm -f "$agent"
echo 'Notifications disabled. State and runtime kept in ~/Library/Application Support/MathModellingMonitor for reinstallation.'
