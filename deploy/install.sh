#!/usr/bin/env bash
set -euo pipefail
# Installs only Race Atlas resources; does not replace system Node or edit other units.
RACE_PROJECT_ROOT=$(cd "$(dirname "$0")/.." && pwd)
if [[ $(id -u) != 0 ]]; then echo 'Run as root to install the Race Atlas system services.' >&2; exit 1; fi
if [[ "$RACE_PROJECT_ROOT" != /root/race ]]; then echo 'Update the unit bind paths before installing from another directory.' >&2; exit 1; fi
RACE_NODE_VERSION=v24.22.2
RACE_NODE_SHA256=48cc0e21e048790e54c0cf5749c2725005313d652651c40b7a21feb9697aaf75
mkdir -p /opt/race/node /srv/race /etc/race-atlas "$RACE_PROJECT_ROOT/.cache" "$RACE_PROJECT_ROOT/data" "$RACE_PROJECT_ROOT/.releases"
if [[ ! -x /opt/race/node/bin/node ]]; then
  curl --fail --silent --show-error --location "https://nodejs.org/dist/$RACE_NODE_VERSION/node-$RACE_NODE_VERSION-linux-x64.tar.xz" --output /tmp/race-node.tar.xz
  echo "$RACE_NODE_SHA256  /tmp/race-node.tar.xz" | sha256sum --check --status
  tar -xJf /tmp/race-node.tar.xz --strip-components=1 -C /opt/race/node
fi
for RACE_SERVICE_USER in race-atlas race-refresh; do
  if ! id "$RACE_SERVICE_USER" >/dev/null 2>&1; then useradd --system --user-group --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin "$RACE_SERVICE_USER"; fi
done
if [[ ! -x /opt/race/venv/bin/python3 ]]; then python3 -m venv /opt/race/venv; fi
/opt/race/venv/bin/python3 -m pip install --disable-pip-version-check -r "$RACE_PROJECT_ROOT/requirements-browser.txt"
PLAYWRIGHT_BROWSERS_PATH=/opt/race/browsers /opt/race/venv/bin/python3 -m playwright install chromium
chown -R race-refresh:race-refresh "$RACE_PROJECT_ROOT/.cache" "$RACE_PROJECT_ROOT/data" "$RACE_PROJECT_ROOT/web/data"
for RACE_RELEASE_DATA in "$RACE_PROJECT_ROOT"/.releases/*/data; do
 if [[ -d "$RACE_RELEASE_DATA" ]]; then chown -R race-refresh:race-refresh "$RACE_RELEASE_DATA"; fi
done
install -m 0644 "$RACE_PROJECT_ROOT"/deploy/race-atlas.service /etc/systemd/system/race-atlas.service
install -m 0644 "$RACE_PROJECT_ROOT"/deploy/race-refresh.service /etc/systemd/system/race-refresh.service
install -m 0644 "$RACE_PROJECT_ROOT"/deploy/race-refresh.timer /etc/systemd/system/race-refresh.timer
install -m 0644 "$RACE_PROJECT_ROOT"/deploy/race-health.service /etc/systemd/system/race-health.service
install -m 0644 "$RACE_PROJECT_ROOT"/deploy/race-health.timer /etc/systemd/system/race-health.timer
install -m 0644 "$RACE_PROJECT_ROOT"/deploy/race-itra.service /etc/systemd/system/race-itra.service
install -m 0644 "$RACE_PROJECT_ROOT"/deploy/race-itra.timer /etc/systemd/system/race-itra.timer
systemctl daemon-reload
systemd-analyze verify /etc/systemd/system/race-atlas.service /etc/systemd/system/race-refresh.service /etc/systemd/system/race-health.service /etc/systemd/system/race-itra.service /etc/systemd/system/race-itra.timer
# Restart only after activating and checking a staged release.
echo 'Units installed. Activate a verified release, then restart race-atlas.service and enable its timers.'
