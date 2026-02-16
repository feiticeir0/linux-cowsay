#!/usr/bin/env bash
set -euo pipefail

WORKDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SYSTEMD_USER_DIR="${HOME}/.config/systemd/user"
SERVICE_FILE="${SYSTEMD_USER_DIR}/cowsay-bluesky.service"
TIMER_FILE="${SYSTEMD_USER_DIR}/cowsay-bluesky.timer"

if [[ "${1:-}" == "" ]]; then
  echo "Usage: $0 <minutes>"
  echo "Example: $0 60"
  exit 1
fi

INTERVAL_MIN="$1"
if ! [[ "$INTERVAL_MIN" =~ ^[0-9]+$ ]] || [[ "$INTERVAL_MIN" -le 0 ]]; then
  echo "Error: minutes must be a positive integer."
  exit 1
fi

mkdir -p "$SYSTEMD_USER_DIR"

cat >"$SERVICE_FILE" <<EOF
[Unit]
Description=Post fortune/cowsay/lolcat to Bluesky

[Service]
Type=oneshot
WorkingDirectory=${WORKDIR}
ExecStart=${WORKDIR}/post_cowsay.py
EOF

cat >"$TIMER_FILE" <<EOF
[Unit]
Description=Run cowsay-bluesky every ${INTERVAL_MIN} minutes

[Timer]
OnBootSec=2min
OnUnitActiveSec=${INTERVAL_MIN}min
Unit=cowsay-bluesky.service
Persistent=true

[Install]
WantedBy=timers.target
EOF

chmod +x "${WORKDIR}/post_cowsay.py"
systemctl --user daemon-reload
systemctl --user enable --now cowsay-bluesky.timer

echo "Installed."
echo "Check status:"
echo "  systemctl --user status cowsay-bluesky.timer"
echo "List timers:"
echo "  systemctl --user list-timers | rg cowsay-bluesky"
