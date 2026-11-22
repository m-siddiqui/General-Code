#!/bin/bash
# Starts Khutbah Live automatically when the Mac Studio logs in, restarts it if it ever
# crashes, and keeps the Mac awake while it runs. Run once:  bash macos/install-autostart.sh
set -euo pipefail
DIR="$(cd "$(dirname "$0")/.." && pwd)"
PY="$(command -v python3)"
PLIST="$HOME/Library/LaunchAgents/org.isnwo.khutbah-live.plist"
mkdir -p "$HOME/Library/LaunchAgents" "$DIR/data"
cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>org.isnwo.khutbah-live</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/caffeinate</string><string>-i</string>
    <string>$PY</string><string>$DIR/server.py</string>
  </array>
  <key>WorkingDirectory</key><string>$DIR</string>
  <key>EnvironmentVariables</key>
  <dict><key>PATH</key><string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string></dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$DIR/data/server.log</string>
  <key>StandardErrorPath</key><string>$DIR/data/server.log</string>
</dict>
</plist>
PLIST
launchctl bootout "gui/$(id -u)/org.isnwo.khutbah-live" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "Installed. Khutbah Live is running: http://$(ipconfig getifaddr en0 2>/dev/null || echo localhost):8080"
echo "Log: $DIR/data/server.log    Uninstall: launchctl bootout gui/$(id -u)/org.isnwo.khutbah-live && rm '$PLIST'"
